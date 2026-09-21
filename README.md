# EvalForge

**Turn a source document into a reviewed, model-tested LLM evaluation dataset.**

EvalForge is a full-stack tool that converts source material (a document
or pasted text) into structured evaluation cases for testing LLM-backed
applications, helps a human reviewer catch weak or duplicate cases before
they're trusted, and then runs the reviewed dataset against a target
model so failures can actually be inspected. Every generated fact traces
back to an exact source chunk, every automated score is a documented
heuristic (never claimed as ground truth), and every evaluation result
is persisted with a snapshot of exactly what was tested.

This is a portfolio project built milestone-by-milestone against
[`EvalForge_PRD_Claude_Code_v1.1.md`](EvalForge_PRD_Claude_Code_v1.1.md),
which is treated as the source of truth for scope and design decisions
throughout. See [`DEMO.md`](DEMO.md) for a guided walkthrough and
[`PORTFOLIO.md`](PORTFOLIO.md) for interview-oriented notes on the key
technical decisions.

## Problem

Teams building LLM-backed features often end up testing them
informally -- a handful of manually-written prompts, checked by eye,
that never grow into a real regression suite. Writing a proper
evaluation dataset by hand is slow, and datasets generated purely by an
LLM are not trustworthy without review: they can be duplicated,
ungrounded in any real source, or simply wrong. EvalForge is a small,
concrete answer to that gap: generate candidate cases from a real
document, surface the specific things a human should check (possible
duplicates, weak grounding), make review fast, and then let the
resulting dataset actually be used to test a model -- with the results
kept, not just glanced at once.

## What EvalForge Does

```text
Upload source document
  -> extract text
  -> chunk into paragraph-sized pieces
  -> generate evaluation cases (LLM, grounded only in those chunks)
  -> validate generated output (Pydantic)
  -> flag semantic duplicates (MiniLM + cosine similarity)
  -> flag weak grounding (reference answer vs. linked evidence)
  -> human review (edit / approve / reject)
  -> export as JSONL or CSV
  -> run the approved dataset against a target model
  -> inspect pass/fail results on a dashboard
```

## Features

- Source ingestion: pasted text, `.txt`, `.md`, text-based `.pdf`
- Deterministic, paragraph-aware chunking (no NLP library)
- LLM-backed case generation (Gemini or a deterministic Mock provider),
  grounded only in the supplied chunks, validated through Pydantic
- Direct, multi-step, and unanswerable case types
- Semantic duplicate detection between questions (local MiniLM, no API)
- Grounding heuristic between a reference answer and its linked evidence
- Human review: edit, approve, reject, with full evidence inspection
- JSONL / CSV export, approved-by-default, with safe filenames
- Model evaluation: run the approved dataset against a target model,
  score answerable cases by semantic similarity and unanswerable cases
  by a structured judge, with results snapshotted for history
- Results dashboard: pass rate, breakdown by test type and difficulty,
  and a dedicated failed-case view -- purely derived from persisted data
- 317 automated backend tests, all offline by default (see Testing)

## Architecture

```mermaid
flowchart LR
    User[User] --> NextJS[Next.js frontend]
    NextJS --> FastAPI[FastAPI backend]
    FastAPI --> PostgreSQL[(PostgreSQL)]
    FastAPI --> Gemini[Gemini API]
    FastAPI --> MiniLM[MiniLM<br/>local, no API]
```

Gemini is only called for case generation, target-model answering, and
unanswerable-case judging -- and only when `USE_MOCK_LLM=false`. MiniLM
runs locally in the backend process for every embedding/similarity
operation; it never leaves the machine and needs no key.

## Data Flow

```mermaid
flowchart LR
    Source[Source Document] --> Chunks[Source Chunks]
    Chunks --> Cases[Evaluation Cases]
    Cases --> Review[Human Review]
    Review --> Approved[Approved Dataset]
    Approved --> Export[JSONL / CSV Export]
    Approved --> Run[Evaluation Run]
    Run --> Results[Evaluation Results]
    Results --> Dashboard[Results Dashboard]
```

## Tech Stack

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic
- **Frontend:** Next.js, TypeScript, React, Tailwind CSS
- **LLM Provider:** Google Gemini, with a deterministic Mock provider for
  development/testing (no Anthropic/OpenAI key needed anywhere)
- **Embeddings:** `sentence-transformers` (`all-MiniLM-L6-v2`), run
  locally for duplicate detection, grounding, and answer scoring -- one
  model, no vector database, no external embedding API

## How It Works

### Embeddings

MiniLM converts a piece of text into a 384-dimensional vector of numbers
positioned so that texts with similar *meaning* point in similar
directions, even when the wording is completely different. It's small
enough to run on a CPU in a fraction of a second, so nothing here needs
a GPU, a hosted embedding API, or a vector database.

### Cosine Similarity

```text
cosine_similarity(A, B) = (A · B) / (||A|| ||B||)
```

The dot product of two vectors, divided by the product of their
lengths. This cancels out vector magnitude and leaves a score from -1
(opposite) to 1 (same direction) -- in practice, almost always positive
for real sentence embeddings. Implemented directly with NumPy
(`app/services/embedding_service.py`) rather than hidden behind a
library call, so the calculation itself stays visible and explainable.

### Duplicate Detection

For every case in a project, the highest cosine similarity between its
`question` and every *other* case's question is stored as
`duplicate_score`. At or above a configurable threshold
(`DUPLICATE_SIMILARITY_THRESHOLD`, default `0.90`), the case is flagged
`is_possible_duplicate` for the reviewer -- advisory only, nothing is
auto-deleted.

### Grounding Heuristic

For each *answerable* case, `reference_answer` is compared (cosine
similarity again) against the exact source chunk(s) linked to that case
at generation time -- never the whole project, never a fresh search.
Below `GROUNDING_SIMILARITY_THRESHOLD` (default `0.40`), the case is
flagged for manual "review grounding." Unanswerable cases have no
reference answer, so their grounding score is always `null`.

### Model Evaluation

For each *approved* case, a target model answers the bare `question` --
never the reference answer, never the duplicate/grounding scores, never
the review status. Answerable cases are scored by cosine similarity
between the model's response and `reference_answer`, against
`ANSWER_SIMILARITY_THRESHOLD` (default `0.75`). Unanswerable cases are
scored by a separate structured judge that checks whether the response
appropriately declines rather than inventing an answer.

## Prerequisites

- Python 3.11+ (built and tested with 3.12)
- Node.js 20+
- A local PostgreSQL server

## Quick Start

```bash
# 1. PostgreSQL
createdb evalforge

# 2. Backend
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set DATABASE_URL to your own PostgreSQL user (see below).
# USE_MOCK_LLM=true by default -- no Gemini key needed to start.
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd web
npm install
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. The backend runs at `http://localhost:8000`
(`/health` should return `{"status":"ok"}`; interactive API docs are at
`/docs`).

### PostgreSQL setup

You need a local PostgreSQL server and one database. On macOS with
Homebrew:

```bash
brew install postgresql
brew services start postgresql
createdb evalforge
```

`DATABASE_URL` must use *your own* PostgreSQL username, not necessarily
`postgres` -- e.g. `postgresql+psycopg2://$(whoami)@localhost:5432/evalforge`
if your local Postgres uses your OS username with no password, or
`postgresql+psycopg2://postgres:postgres@localhost:5432/evalforge` if
you're running a `postgres`-user setup (e.g. a default Docker Postgres
image). Check `psql -l` or your Postgres install docs if unsure.

### Schema setup (Alembic)

Schema is managed by Alembic migrations, not by the app auto-creating
tables at startup:

```bash
cd api
alembic upgrade head
```

This is the normal path for every fresh database. See "Database
Migrations" below for the full migration history and how to upgrade an
existing pre-Alembic database.

## Using Mock Mode

**Recommended for first-time setup.** With `USE_MOCK_LLM=true` (the
`.env.example` default), the app uses a deterministic fixture provider
instead of calling Gemini: generation, target-model answering, and
unanswerable-case judging all return fixed, repeatable output. This
means the entire pipeline -- generation, review, duplicate/grounding
detection (which always run locally via MiniLM, mock mode or not),
export, evaluation, and the dashboard -- works immediately with no API
key, no quota, and no cost. Mock mode is intended for development and
demos, not as a stand-in for real model quality.

## Using Gemini

To use real Gemini calls, set in `api/.env`:

```text
USE_MOCK_LLM=false
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
Configure a Gemini model available to your account -- the default above
is what this project was built and tested against, but model
availability can change; adjust if it's no longer offered to you. A
missing key with `USE_MOCK_LLM=false` fails with a clear error rather
than crashing.

## Configuration

See `.env.example` (root overview), `api/.env.example`, and
`web/.env.example`. Never commit a real `.env`/`.env.local` file --
`.gitignore` excludes every `.env` variant except the `.env.example`
templates.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_PROVIDER` | LLM provider to use (`gemini`) |
| `GEMINI_API_KEY` | Google AI Studio API key (leave empty with `USE_MOCK_LLM=true`) |
| `GEMINI_MODEL` | Configurable Gemini model identifier |
| `USE_MOCK_LLM` | When `true`, use deterministic fixtures instead of live LLM calls |
| `MAX_GENERATION_CASES` | Upper bound on cases requested per generation call (default `50`) |
| `MAX_EVALUATION_CASES` | Upper bound on approved cases evaluated per run (default `50`) |
| `MAX_UPLOAD_SIZE_MB` | Max size for a source file upload / pasted text body (default `10`) |
| `CHUNK_TARGET_WORDS` / `CHUNK_MAX_WORDS` | Chunking target/ceiling word counts (default `750`/`1000`) |
| `EMBEDDING_MODEL` | sentence-transformers model (default `all-MiniLM-L6-v2`) |
| `DUPLICATE_SIMILARITY_THRESHOLD` | Cosine similarity (0.0–1.0) flagging a possible duplicate (default `0.90`) |
| `GROUNDING_SIMILARITY_THRESHOLD` | Cosine similarity (0.0–1.0) below which grounding is flagged (default `0.40`) |
| `ANSWER_SIMILARITY_THRESHOLD` | Cosine similarity (0.0–1.0) at/above which an answerable result passes (default `0.75`) |
| `CORS_ORIGINS` | Origins allowed to call the API from a browser |
| `NEXT_PUBLIC_API_URL` | Backend base URL the frontend calls (default `http://localhost:8000`) |

## Database Migrations

Schema is managed with **Alembic** (`api/alembic/`), not by the app
auto-creating tables at startup. After changing a model, generate and
apply a migration:

```bash
cd api
source .venv/bin/activate
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Always read an autogenerated migration before applying it -- this
project hit a real bug where autogenerate used generic `sa.Enum(...)`
for a column reusing an existing PostgreSQL enum type, which silently
ignores `create_type=False` and tries to recreate the type. The fix was
`sqlalchemy.dialects.postgresql.ENUM(..., create_type=False)`.

Migration history:

```text
e623519c2fcd  baseline schema (M0-M5)
  -> ca38c3fad961  add duplicate_score to evaluation_cases (M6)
  -> 11ae2c5fcf05  add grounding_score to evaluation_cases (M7)
  -> ba26d2f7caa7  add evaluation_runs and evaluation_results (M9, head)
```

To upgrade an existing local database created before Alembic was
introduced (via `Base.metadata.create_all()`), mark it as already at the
pre-Alembic baseline, then apply everything after it:

```bash
alembic stamp e623519c2fcd
alembic upgrade head
```

## Dataset Generation

An LLM provider (Gemini or Mock) is given only the source chunks for a
small batch and asked to produce evaluation cases in a fixed JSON shape.
Every returned case is validated through a Pydantic model
(`GeneratedCase`) before it's trusted -- structurally invalid output, or
a case referencing a chunk outside the batch, is rejected and retried
once. Only a fully valid batch is persisted; nothing partial is saved.
Three case types are supported: **direct** (single-chunk fact), **multi-step**
(combines up to two chunks), and **unanswerable** (deliberately asks
something the source doesn't cover, with `reference_answer` forced to
`null` so nothing is invented).

## Duplicate Detection

See "How It Works" above. Recalculated for the whole project after
generation and after any question edit, project-isolated, using one
batched MiniLM call rather than one call per question.

## Grounding Heuristic

See "How It Works" above. Recalculated after generation and after any
edit to `reference_answer`/answerability (not after edits to unrelated
fields like category or difficulty).

## Dataset Review

Every generated case starts in `generated` status. A reviewer can edit
any field, then move a case to `approved` or `rejected`. Edits are
re-validated with the same rules generation itself enforces (e.g. an
unanswerable case can't carry a reference answer). Only `approved` cases
are ever exported or evaluated by default.

## Export

`GET /projects/{project_id}/export?format=jsonl|csv&status=approved|generated|rejected|all`
-- reads already-stored data only, never recalculates scores or calls
any model. JSONL is one JSON object per line (not an array); CSV is
written with Python's `csv` module, never hand-built strings.
Unanswerable cases export `reference_answer` as `null` (JSONL) or a
blank cell (CSV) -- never a UI display string. Filenames are slugified
to `[a-z0-9-]` before being placed in `Content-Disposition`, so a
project name can never cause header injection or path traversal.

## Model Evaluation

`POST /projects/{project_id}/evaluations` runs every approved case
through the configured provider and persists one `EvaluationRun` plus an
`EvaluationResult` per case, only once every case has a response and a
score -- a failed run (provider error, or judge output still malformed
after one retry) leaves nothing behind. Each result **snapshots** its
question/reference answer/test type/difficulty as they were at
evaluation time, so editing a case later never rewrites a historical
result's meaning. See "How It Works" for scoring details.

**Limitation, measured directly:** `similarity(reference, a
differently-worded-but-correct answer) = 0.9428`, but
`similarity(reference, a same-wording answer with a changed number) =
0.9208` -- still comfortably above the pass threshold despite being
factually wrong. Semantic similarity measures topical/wording
relatedness, not fact-checking, and this project is explicit about that
rather than presenting a "Pass" as a correctness guarantee.

## Results Dashboard

`GET /evaluations/{evaluation_id}/dashboard` -- purely derived analytics
computed by counting/grouping already-persisted `EvaluationResult` rows.
It never calls Gemini, never recalculates MiniLM similarity, and never
touches `duplicate_score`/`grounding_score`. The dashboard shows total/
passed/failed/pass rate, a breakdown by test type and by difficulty (a
category with zero cases shows "N/A", never a misleading `0%`), a
dedicated Failed Cases section with full detail on every failure, and a
filterable all-results list. No charting library is used -- every bar is
a plain CSS width. Project pages list previous runs with pass rate and
link to each one's dashboard.

## Testing

```bash
cd api
source .venv/bin/activate
pytest
```

**317 automated backend tests** (314 in the default run + 3 marked
`real_model`). The default run makes **zero live Gemini calls and zero
MiniLM network/model access** -- providers are mocked and embeddings are
faked with a deterministic hash-based stand-in, so the suite runs fully
offline. The 3 `real_model`-marked tests actually load MiniLM and are
excluded by default (`pytest.ini`'s `addopts = -m "not real_model"`):

```bash
pytest -m real_model
```

Frontend:

```bash
cd web
npm run lint
npx tsc --noEmit
npm run build
```

## Demo

See [`DEMO.md`](DEMO.md) for a full guided walkthrough (~4-5 minutes)
using the fictional source document at
[`examples/employee_handbook.md`](examples/employee_handbook.md), with
speaking notes for each step. A real JSONL export from that exact flow
is checked in at [`examples/sample_dataset.jsonl`](examples/sample_dataset.jsonl).

## Project Structure

```text
evalforge/
├── api/
│   ├── app/
│   │   ├── api/        # FastAPI routers (one file per resource)
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic request/response schemas
│   │   ├── providers/  # LLMProvider abstraction (Gemini, Mock)
│   │   └── services/   # Business logic, orchestration, aggregation
│   ├── alembic/         # Schema migrations
│   └── tests/           # 317 backend tests
├── web/
│   ├── app/             # Next.js App Router pages + components
│   └── lib/             # API client, shared formatting
├── examples/            # Demo source document + sample export
├── DEMO.md
├── PORTFOLIO.md
├── README.md
└── EvalForge_PRD_Claude_Code_v1.1.md
```

## Limitations

- **Semantic similarity is not factual correctness.** A reworded correct
  answer and a same-wording answer with a changed number (`25 days` vs.
  `20 days`) can both score highly. See the measured example above.
- **Grounding is heuristic.** A semantically related but factually
  incorrect answer may not be flagged for review.
- **Synthetic cases require human review.** Generated questions/answers
  can be poor, ambiguous, or trivially easy -- the review step exists
  because generation output is a first draft, not a finished dataset.
- **PDF support is text-layer only.** No OCR, so scanned/image-only PDFs
  extract no text.
- **Small-scale by design.** Built for student-scale datasets (tens of
  cases, one reviewer at a time), not thousands of concurrent users --
  see `PORTFOLIO.md` for why that made an in-memory O(n²) comparison and
  a single-process backend the right call here, not a vector database or
  microservices.
- **No authentication.** Not required for a local portfolio demo.
- **No model-vs-model comparison, leaderboard, or trend-over-time
  analytics** -- one run at a time, by design (see Future Improvements).

## Future Improvements

- Model-vs-model comparison (run the same dataset against two providers
  and compare results side by side)
- An optional LLM-as-judge scoring mode for answerable cases, as an
  alternative to pure semantic similarity
- OCR support for scanned/image-only PDFs
- Authentication and multi-user project ownership
- Downloadable evaluation-run reports (PDF/HTML) from the dashboard

## Portfolio Notes

See [`PORTFOLIO.md`](PORTFOLIO.md) for a suggested CV bullet, the
technical concepts this project is meant to demonstrate, and why it
deliberately avoids a vector database, microservices, Kubernetes,
agents, and custom model training.
