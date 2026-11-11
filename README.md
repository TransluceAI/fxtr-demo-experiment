# fxtr demo experiment

This fxtr experiment generates group chat messages and rates their hostility. GPT-6 Luna and
GPT-5.6 Luna each apply two rubrics to every message. If the models assign different severity
labels under the same rubric, GPT-6 Luna rates that message again.
[Experiment design](EXPERIMENT.md)

## Run locally

Install uv and Python 3.13. You need PostgreSQL and an OpenAI API key with access to both models.
Clone the repository, enter its directory, and install the locked dependencies.

```sh
uv sync --locked
```

Point fxtr at a database where it can create its schema. If you need a local Postgres instance,
the following command starts one on port 55433 with credentials for local development.

```sh
docker run --name fxtr-demo-postgres -d -p 127.0.0.1:55433:5432 \
  -e POSTGRES_DB=fxtr -e POSTGRES_USER=fxtr -e POSTGRES_PASSWORD=fxtr postgres:17
```

Once Postgres accepts connections, initialize the project. Substitute your own database URL if needed.

```sh
uv run fxtr init --database-url postgresql+asyncpg://fxtr:fxtr@localhost:55433/fxtr
```

Set `OPENAI_API_KEY` in your environment or in an ignored `.env` file at the project root.
Start with a small live run. Each message requests four primary judgments and up to two tiebreakers.

```sh
uv run python launch.py --messages 3
```

Start the viewer with `uv run fxtr view` in a second terminal. Open the job to inspect messages,
the four primary judgments for each message, and any tiebreakers. To run a larger sample:

```sh
uv run python launch.py --messages 256 --concurrency 128
```

The launcher prints judgment counts, token usage, and timings. Each run uses a fresh cache root
by default. To reuse results, repeat the same inputs with `--root <previous-root>`.

fxtr pins a Git commit for each job. After local edits, commit them or stage them and pass
`--allow-staged`.
