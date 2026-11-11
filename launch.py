"""Measure fxtr throughput with simulated generation and live severity tiebreakers."""

import argparse
import os
from time import perf_counter, process_time
from uuid import uuid4

import anyio
from behaviors.types import ReasoningParams, SamplingParams
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.project.client import JobID
from fxtr.project.running import wait_for_job
from fxtr.runner.postgres.client import LocalProjectClient
from fxtr.runner.postgres.runner import RunLimits
from sqlalchemy import text

from message_judge_bench import make_messages
from message_judge_bench.judge import RUBRICS, JudgeConfig
from message_judge_bench.pipeline import PRIMARY_MODEL, SECOND_MODEL, message_judgments

MODELS = (PRIMARY_MODEL, SECOND_MODEL)


async def report_overlap(
    client: LocalProjectClient, job_id: JobID, messages: int, ties: int
) -> None:
    """Measure overlap at both dependencies using successful attempts from this job."""
    query = text("""
    WITH runs AS (
        SELECT n.name, s.key, a.started_at, a.finished_at
        FROM workflow_invocations i
        JOIN spawns s ON s.invocation_id = i.id
        JOIN node_names n ON n.invocation_id = i.id AND n.identity = s.node_identity
        JOIN job_step_bindings b ON b.job_id = i.job_id AND b.cache_key = s.step_cache_key
        JOIN attempts a ON a.id = b.step_result_id
        JOIN job_attempts j ON j.id = a.owner_job_attempt_id AND j.job_id = i.job_id
        WHERE i.job_id = :job_id AND s.key <> '[]'::jsonb
    ), pairs AS (
        SELECT key->>0 AS message, key->>-1 AS rubric,
               min(started_at) FILTER (WHERE name = 'judge') AS first_start,
               max(started_at) FILTER (WHERE name = 'judge') AS both_started,
               max(finished_at) FILTER (WHERE name = 'judge') AS both_finished,
               max(started_at) FILTER (WHERE name = 'tiebreaker') AS tie_start
        FROM runs WHERE name IN ('judge', 'tiebreaker') GROUP BY 1, 2
    ), timing AS (
        SELECT p.*, g.finished_at AS generated
        FROM pairs p JOIN runs g ON g.name = 'simulate_generate_message' AND g.key->>0 = p.message
    )
    SELECT (SELECT count(*) FROM runs) AS measured,
           count(*) FILTER (WHERE both_started < (SELECT max(generated) FROM timing))
               AS primary_overlap,
           count(*) FILTER (WHERE tie_start < (SELECT max(both_finished) FROM timing))
               AS tie_overlap,
           count(*) FILTER (WHERE first_start < generated OR tie_start < both_finished)
               AS out_of_order
    FROM timing
    """)
    async with client.database.transaction() as tx:
        counts = (await tx.execute(query, {"job_id": job_id})).mappings().one()
    pairs = messages * len(RUBRICS)
    expected = messages + pairs * len(MODELS) + ties
    if counts["measured"] != expected:
        print(f"overlap unavailable: {counts['measured']}/{expected} mapped steps ran in this job")
        return
    if counts["out_of_order"]:
        raise ValueError(f"Inputs were not ready for {counts['out_of_order']} message/rubric pairs")
    print(f"pairs_with_both_primaries_before_last_generation={counts['primary_overlap']}/{pairs}")
    if ties:
        print(f"tiebreakers_started_before_last_primary_finished={counts['tie_overlap']}/{ties}")


async def run(args: argparse.Namespace) -> None:
    root = args.root or f"live-message-judge-{uuid4().hex}"
    async with LocalProjectClient.from_project(
        __file__, limits=RunLimits(steps=args.concurrency)
    ) as client:
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("Set OPENAI_API_KEY in the environment or in the project's .env.")
        print(
            f"models={','.join(MODELS)} rubrics={','.join(RUBRICS)} root={root} "
            f"messages={args.messages:,} concurrency={args.concurrency}",
            flush=True,
        )
        started = perf_counter()
        cpu_started = process_time()
        rows = make_messages(args.messages)
        sampling = SamplingParams(
            max_tokens=4000, reasoning=ReasoningParams(enabled=True, effort="low")
        )
        configs = {
            (model, rubric): await client.store(
                JudgeConfig(model_name=model, prompt=prompt, sampling=sampling)
            )
            for model in MODELS
            for rubric, prompt in RUBRICS.items()
        }
        prepared = perf_counter()
        handle = await client.submit(
            message_judgments,
            {
                "messages": rows,
                "judges": Array.from_items(
                    configs.items(), ("[model: str, rubric: str]", BoundID[JudgeConfig])
                ),
            },
            root=root,
            allow_staged=args.allow_staged,
        )
        submitted = perf_counter()
        del rows
        result = await wait_for_job(client, handle, open_browser=False)
        finished = perf_counter()
        cpu = process_time() - cpu_started
        summary = result.item()
        pairs = args.messages * len(RUBRICS)
        if summary["message_rubric_pairs"] != pairs:
            raise ValueError(
                f"Expected {pairs} message/rubric pairs, got {summary['message_rubric_pairs']}"
            )
        ties = summary["tiebreakers"]
        calls = pairs * len(MODELS) + ties
        elapsed = finished - started
        print(
            f"judgments={calls} tiebreakers={ties}/{pairs} ({ties / pairs:.1%}) "
            f"incomplete={summary['incomplete']} unresolved={summary['unresolved']} "
            f"uncached_input_tokens={summary['input_tokens']} "
            f"output_tokens={summary['output_tokens']}"
        )
        print(
            f"prepare={prepared - started:.2f}s submit={submitted - prepared:.2f}s "
            f"wait={finished - submitted:.2f}s total={elapsed:.2f}s "
            f"process_cpu={cpu:.2f}s throughput={args.messages / elapsed:.1f} messages/s "
            f"({calls / elapsed:.1f} judgments/s)"
        )
        await report_overlap(client, handle.job_id, args.messages, ties)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--messages",
        type=int,
        default=16,
        help="generated messages for the two-model, two-rubric sweep (default 16)",
    )
    parser.add_argument("--concurrency", type=int, default=128)
    parser.add_argument("--root", help="reuse this cache namespace (default: fresh per launch)")
    parser.add_argument(
        "--allow-staged", action="store_true", help="allow fxtr to pin staged edits"
    )
    args = parser.parse_args()
    if args.messages < 1 or args.concurrency < 1:
        parser.error("messages and concurrency must be positive")
    anyio.run(run, args)
