# EvalForge Demo

A ~4-5 minute walkthrough of the full EvalForge pipeline, from a source
document to a scored, dashboard-ready evaluation run. Every step below
was verified against a real running instance (PostgreSQL + FastAPI +
Next.js) with `USE_MOCK_LLM=true`, so it is reproducible without a
Gemini API key, quota, or cost.

## Before you start

Follow the README's Quick Start first: PostgreSQL running, `alembic
upgrade head` applied, backend on `http://localhost:8000` with
`USE_MOCK_LLM=true`, frontend on `http://localhost:3000`.

The demo source document is [`examples/employee_handbook.md`](examples/employee_handbook.md)
-- a short, entirely fictional company handbook created for this demo.
It contains clear facts (for direct questions), facts that span two
sections (for multi-step questions), and topics it deliberately never
mentions, such as parental leave or retirement benefits (for
unanswerable questions).

A real JSONL export produced by this exact flow (in Mock mode) is
checked in at [`examples/sample_dataset.jsonl`](examples/sample_dataset.jsonl),
so you can see the target shape without running anything.

## Demo Flow

### 1. Open EvalForge

Go to `http://localhost:3000`. The home page lists existing projects and
shows whether the backend is reachable.

> *"EvalForge turns a source document into a reviewed, model-tested
> evaluation dataset -- this is the project list where that all starts."*

### 2. Create "Employee Handbook Evaluation"

Click **Create Project**, name it, and open it.

> *"A project is just a container for one source document and the
> evaluation dataset generated from it."*

### 3. Upload `employee_handbook.md`

Click **Upload File**, choose `examples/employee_handbook.md`, and
submit.

> *"The file is stored as-is and its full text extracted immediately --
> for a text-based PDF the same extraction happens with `pypdf`, no
> OCR."*

### 4. Show the extracted source

Click **View** on the uploaded source to see the full stored text and
metadata (character count, chunk count).

> *"This is the ground truth every later evaluation case has to trace
> back to."*

### 5. Show the chunks

Scroll to the Chunks section on the same page.

> *"Chunking is deterministic and paragraph-aware -- no NLP library,
> just accumulating paragraphs up to a target word count so each chunk
> stays coherent. This handbook becomes two chunks."*

### 6. Generate 10 evaluation cases

Back on the project page, click **Generate Evaluation Dataset**, set
count to 10, and submit.

> *"The provider only ever sees the source chunks -- never the rest of
> the internet -- so every generated question and answer is grounded in
> this document specifically."*

### 7. Show the direct / multi-step / unanswerable mix

Point out cases tagged `direct`, `multi_step`, and `unanswerable` in the
list.

> *"Direct cases test a single fact, multi-step cases combine two
> chunks, and unanswerable cases deliberately ask something the source
> never covers -- a good evaluation model should recognize that,
> instead of inventing an answer."*

### 8. Show a duplicate warning

Point out a case with an amber **Possible duplicate** badge.

> *"This is MiniLM cosine similarity between this question and every
> other question in the project, run entirely locally -- no API call.
> It's a hint for the reviewer, not an automatic rejection."*

### 9. Show a grounding warning

Point out a case with an orange **Review grounding** badge.

> *"Same idea, different comparison: the reference answer against its
> own linked evidence. A low score means the wording drifted from the
> source -- it doesn't necessarily mean the answer is wrong."*

### 10. Open source evidence

Click **View Evidence** on any case.

> *"This is the exact chunk (or two chunks, for a multi-step case) the
> case was generated from -- not a fresh search, the literal evidence
> used at generation time."*

### 11. Edit a weak case

Click **Edit** on a case, tweak its question, and save.

> *"Generated cases are a first draft. A human is expected to fix,
> reject, or approve every one before it's trustworthy."*

### 12. Approve several cases

Click **Approve** on most of the remaining cases.

### 13. Reject one case

Click **Reject** on one case.

> *"Only approved cases ever get exported or evaluated -- generated and
> rejected cases are excluded by default everywhere downstream."*

### 14. Export JSONL

Scroll to Export Dataset, leave Format as JSONL and Cases as Approved,
and click **Download**.

> *"One JSON object per line, with the underlying duplicate/grounding
> scores included -- never the API key, never the full source text."*

### 15. Run model evaluation

Scroll to Model Evaluation, note the approved-case count and Mock
provider label, and click **Run Evaluation**.

> *"The target model gets only the question -- never the reference
> answer or any of the review metadata -- so it has to answer
> independently, just like a real end user would ask it."*

### 16. Open the results dashboard

Click **View results** after the run completes.

> *"Everything here is read from what was just persisted -- the
> dashboard never reruns or rescoring anything, it's pure aggregation:
> totals, pass rate, and a breakdown by test type and difficulty."*

### 17. Show a failed case

Scroll to Failed Cases and open one.

> *"This is the part that actually matters for evaluating a model: not
> just the pass rate, but exactly which question it got wrong, what it
> answered, and why that was scored a failure."*

## Optional: switch to Gemini

Everything above also works with a real Gemini key: set
`USE_MOCK_LLM=false`, `GEMINI_API_KEY=<your key>` in `api/.env`, restart
the backend, and repeat steps 6 and 15. Generation and evaluation will
call the real Gemini API instead of returning fixture data; everything
else in the flow is identical.
