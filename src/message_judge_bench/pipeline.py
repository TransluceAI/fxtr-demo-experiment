"""Simulate message generation and break ties between two live hostility judgments."""

import random
from typing import Annotated, TypedDict

import anyio
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.entity_defns.query import value
from fxtr.experiment.handles import ArrayHandle
from fxtr.experiment.steps import StepContext, step
from fxtr.experiment.workflows import WorkflowContext, workflow

from . import ChatMessage
from .judge import SEVERITIES, JudgeConfig, VerdictRow, judge_message

PRIMARY_MODEL = "gpt-6-luna"
SECOND_MODEL = "gpt-5.6-luna"
CHARS_PER_SECOND = 200


@step(name="bench.simulate_generate_message")
async def simulate_generate_message(context: StepContext, message: ChatMessage) -> ChatMessage:
    """Emit a message after its simulated generation delay."""
    base_delay = len(message["text"]) / CHARS_PER_SECOND
    multiplier = random.Random(message["id"]).uniform(0.8, 1.2)
    await anyio.sleep(base_delay * multiplier)
    return message


class Summary(TypedDict):
    message_rubric_pairs: int
    tiebreakers: int
    incomplete: int
    unresolved: int
    input_tokens: int
    output_tokens: int
    severity: BoundID[Array]


Verdicts = Annotated[Array[VerdictRow], "[message: str, rubric: str]"]


@step(name="bench.summarize_tiebreaks")
async def summarize(
    context: StepContext, first: Verdicts, second: Verdicts, tiebreaker: Verdicts
) -> Summary:
    """Resolve each severity vote and total the usage of judgments actually made."""
    severity = {}
    tiebreaks = incomplete = input_tokens = output_tokens = 0
    for (key, a), (second_key, b) in zip(first.items(), second.items(), strict=True):
        if key != second_key:
            raise ValueError("Primary judges returned different message keys")
        left, right = a["hostility"], b["hostility"]
        tie = tiebreaker.get(key)
        disagree = left is not None and right is not None and left != right
        if disagree != (tie is not None):
            raise ValueError(f"Unexpected tiebreaker coverage for {key}")
        final = left if left == right else None
        if tie is not None:
            tiebreaks += 1
            third = tie["hostility"]
            if left is not None and right is not None and third is not None:
                final = sorted((left, right, third), key=SEVERITIES.index)[1]
        severity[key] = final
        for verdict in (a, b, tie):
            if verdict is not None:
                incomplete += not verdict["complete"]
                input_tokens += verdict["input_tokens"]
                output_tokens += verdict["output_tokens"]
    if tiebreaks != len(tiebreaker):
        raise ValueError("Tiebreaker returned an unknown message key")
    return Summary(
        message_rubric_pairs=len(first),
        tiebreakers=tiebreaks,
        incomplete=incomplete,
        unresolved=sum(value is None for value in severity.values()),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        severity=await context.store(
            Array.from_items(severity.items(), ("[message: str, rubric: str]", str | None))
        ),
    )


@workflow(name="bench.message_judgments")
async def message_judgments(
    context: WorkflowContext,
    messages: Annotated[ArrayHandle[ChatMessage], "[message: str]"],
    judges: Annotated[ArrayHandle[BoundID[JudgeConfig]], "[model: str, rubric: str]"],
) -> Annotated[ArrayHandle[Summary], "[]"]:
    """Run both models on both rubrics and break model disagreements within each rubric."""
    generated = context.run_step(
        "simulate_generate_message",
        simulate_generate_message,
        {"message": messages},
        map_over=["message"],
    )
    ratings = context.run_step(
        "judge",
        judge_message,
        {"config": judges, "message": generated},
        map_over=["message", "model", "rubric"],
    )
    first = ratings.sel({"model": PRIMARY_MODEL}).collect()
    second = ratings.sel({"model": SECOND_MODEL}).collect()
    votes = context.combine({"message": generated, "first": first, "second": second})
    disputed = (
        votes.filter(
            value().field("first").field("hostility") != value().field("second").field("hostility")
        )
        .field("message")
        .collect()
    )
    third = context.run_step(
        "tiebreaker",
        judge_message,
        {
            "config": judges.sel({"model": PRIMARY_MODEL}).collect(),
            "message": disputed,
        },
        map_over=["message", "rubric"],
        join="inner",
    )
    return context.run_step(
        "summarize", summarize, {"first": first, "second": second, "tiebreaker": third}
    )
