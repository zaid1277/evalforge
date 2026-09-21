# EvalForge — Portfolio Notes

Supporting notes for discussing this project in a resume, cover letter,
or technical interview. See `README.md` for the project itself and
`DEMO.md` for a walkthrough.

## Short CV version

> Built a full-stack LLM evaluation platform (FastAPI, PostgreSQL,
> Next.js, Gemini, MiniLM) that turns source documents into structured
> test datasets, detects semantic duplicates and grounding issues,
> supports human review and export, and runs the reviewed dataset
> against a target model with a persisted results dashboard.

## Key concepts I should be able to explain

- **Embeddings** — a piece of text mapped to a fixed-length vector of
  numbers such that texts with similar meaning point in similar
  directions. Used here via `sentence-transformers`' `all-MiniLM-L6-v2`,
  running locally (no API call, no key).
- **Cosine similarity** — `(A · B) / (||A|| ||B||)`, the cosine of the
  angle between two vectors. Independent of vector magnitude, so it
  measures *direction* (meaning), not length. Implemented manually with
  NumPy rather than hidden behind a library call, on purpose.
- **MiniLM** — a small, distilled sentence-transformer model. Chosen for
  this project specifically because it runs fast on a CPU with no GPU
  and no external API, which matters for a local, zero-cost student
  project.
- **Duplicate detection** — pairwise cosine similarity between every
  question in a project (O(n²), fine at this scale — see below), highest
  score per case stored as `duplicate_score`, thresholded into an
  advisory `is_possible_duplicate` flag computed on read, never stored.
- **Grounding heuristic** — cosine similarity between a reference answer
  and its own linked source evidence (not the whole project, not a fresh
  search). A heuristic for "does the wording relate to the evidence,"
  not a factual-correctness check — a known, deliberately documented
  limitation.
- **LLM structured output** — Gemini calls request
  `response_mime_type="application/json"`; every response is parsed and
  validated through Pydantic before anything is trusted or persisted.
  Malformed output is retried at most once, never silently accepted.
- **Pydantic validation as a trust boundary** — `GeneratedCase` and
  `JudgeVerdict` are the exact points where raw LLM output either
  becomes real data or gets rejected. Nothing from a provider reaches
  the database without passing through one of these first.
- **Provider abstraction** — a small `LLMProvider` ABC
  (`generate_eval_cases`, `generate_response`,
  `judge_unanswerable_response`) with `GeminiProvider` and
  `MockProvider` implementations, selected by one factory function.
  Generation and evaluation are separate methods/prompts on purpose,
  even though both call an LLM — they're different tasks (source →
  question vs. question → answer).
- **SQL relationships and cascades** — `Project → SourceDocument →
  SourceChunk`, `Project → EvaluationCase → EvaluationCaseSource →
  SourceChunk`, and `Project → EvaluationRun → EvaluationResult →
  EvaluationCase`, all with `ondelete="CASCADE"` at the database level
  plus matching ORM `cascade="all, delete-orphan"`, so deleting a
  project cleanly removes everything under it.
- **Alembic migrations** — schema changes are explicit, reviewed
  migration files, not `Base.metadata.create_all()` against a live
  database. Includes a real bug found and fixed during development:
  reusing an existing PostgreSQL enum type across two tables requires
  the dialect-specific `postgresql.ENUM(..., create_type=False)`, not
  generic `sa.Enum(...)`, which silently ignores that flag and tries to
  recreate the type.
- **Test isolation** — every test runs against a dedicated
  `..._test`-suffixed database via a FastAPI dependency override, with
  tables created/dropped per test. A real incident during development
  (a test that constructed its own DB session instead of using the
  fixture, and wrote to the *real* dev database) is exactly why this
  matters, not just theoretical hygiene.
- **Evaluation snapshots** — `EvaluationResult` copies the question,
  reference answer, test type, and difficulty as they were *at
  evaluation time*, rather than only pointing at the live
  `EvaluationCase`. Editing a case later never rewrites the meaning of a
  historical evaluation result.
- **The semantic-similarity limitation** — the single most important
  thing to be able to explain about this project: cosine similarity
  measures topical/wording relatedness, not factual correctness. Real
  measured example — a correct rephrasing scores `~0.94`, but a
  same-wording answer with a *changed number* still scores `~0.92`,
  comfortably above the pass threshold. This is documented in the code,
  the README, and surfaced as a disclaimer on the dashboard itself,
  rather than hidden.

## Architecture decisions (and why not the "bigger" option)

- **No vector database.** Dataset sizes here are small by design
  (typically 10–50 cases, capped by `MAX_GENERATION_CASES`/
  `MAX_EVALUATION_CASES`), so an O(n²) in-memory cosine comparison over
  a NumPy array is simpler, easier to explain, and fast enough — a
  vector database would add real operational complexity to solve a
  performance problem this project doesn't have.
- **No microservices.** One FastAPI process and one Next.js process is
  enough surface area for one developer to reason about end to end, and
  splitting it further wouldn't change what the system does.
- **No Kubernetes / container orchestration.** There's no multi-node
  deployment or autoscaling need here — `uvicorn` and `next dev`/`next
  start` are sufficient, and adding orchestration would be complexity
  without a corresponding requirement.
- **No agents.** Every LLM call in this project has one clear job
  (generate cases from evidence, answer a question, judge a response) —
  there's no multi-step autonomous planning problem that would justify
  an agent framework.
- **No custom model training.** The evaluation approach here is
  measuring an existing model's behavior against a dataset, not
  producing a new one — training isn't the problem being solved.

## What I'd do next if this weren't scoped as an MVP

See the README's "Future Improvements" section — model-vs-model
comparison, an LLM-as-judge option for answerable cases, richer PDF
handling (OCR for scanned documents), and authentication for a
multi-user deployment are the most natural next steps, each deliberately
deferred rather than overlooked.
