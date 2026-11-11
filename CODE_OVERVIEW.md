# Code overview

- `src/message_judge_bench/__init__.py` builds seeded synthetic group-chat messages with up to five prior posts from the same room.
- `src/message_judge_bench/judge.py` defines both rubrics, the shared JSON reply format, model calls through behaviors, and verdict parsing. Each verdict includes the raw reply and the token counts.
- `src/message_judge_bench/pipeline.py` simulates generation latency, maps the judge over message × model × rubric, selects disputed pairs, and uses the same judge step for tiebreakers. The summary links to final severities by message and rubric.
- `launch.py` constructs the four model/rubric configurations, submits the workflow, and reads step start and finish times from the fxtr Postgres attempt tables.
