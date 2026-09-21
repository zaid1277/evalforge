# EvalForge — Automated Evaluation Dataset Generator
## Product Requirements Document (PRD)

**Project Type:** Full-stack AI/ML portfolio project  
**Target Developer Level:** 3rd-year Computer Science student  
**Primary Development Tool:** Claude Code  
**Scope:** Realistic student project with a polished, demonstrable MVP  
**Document Version:** 1.1

---

# 1. Project Summary

EvalForge is a web application that automatically converts source material into structured evaluation datasets for testing Large Language Model (LLM) applications.

A user uploads a source document or pastes text. EvalForge extracts and chunks the content, uses an existing LLM to generate evaluation cases, performs basic automated quality checks, allows the user to review the generated examples, and exports the final dataset.

An optional evaluation feature allows the user to run another LLM against the dataset and view simple performance results.

The project should demonstrate practical AI engineering without pretending to train a foundation model from scratch.

The application should also be inexpensive to develop and demo. The default development path should work with a Gemini API key from Google AI Studio and should favor free-tier or low-cost models where practical.

The core student-built engineering work is:

- document ingestion
- text processing and chunking
- structured LLM generation
- Pydantic validation
- embeddings
- cosine similarity
- semantic duplicate detection
- simple grounding heuristics
- PostgreSQL persistence
- REST API design
- frontend development
- evaluation logic
- automated testing
- clear documentation

---

# 2. Project Goal

Build a believable portfolio project that answers this problem:

> Creating evaluation datasets for AI applications manually is slow. EvalForge helps developers generate a first-pass evaluation dataset from trusted source material, validate it, review it, and use it to test an LLM.

The project should look technically strong on a CV while remaining realistic for one university student to understand, explain, and maintain.

---

# 3. Non-Goals

Claude Code must NOT expand the MVP into an enterprise AI platform.

The following are explicitly out of scope for the initial release:

- training a custom LLM
- fine-tuning a foundation model
- distributed computing
- Kubernetes
- microservices
- Kafka
- Redis unless genuinely required later
- complex authentication
- organization/team accounts
- billing
- multi-tenant architecture
- custom vector database
- large-scale web crawling
- OCR for scanned PDFs
- video/audio ingestion
- complex RAG architecture
- autonomous agents
- reinforcement learning
- custom model training
- enterprise role-based permissions
- real-time collaboration
- production cloud infrastructure

If Claude Code proposes one of these during MVP development, prefer the simpler solution.

---

# 4. Main User Story

As a developer testing an AI application, I want to upload trusted reference material and automatically generate structured evaluation examples so that I can test whether an LLM answers questions accurately and avoids hallucinating.

---

# 5. Secondary User Story

As a developer, I want to run an LLM against my generated dataset so that I can see which evaluation cases it passes or fails.

---

# 6. MVP User Flow

```text
Create Project
      ↓
Add Source Material
      ↓
Extract + Clean Text
      ↓
Chunk Source
      ↓
Choose Generation Settings
      ↓
Generate Evaluation Cases
      ↓
Validate Cases
      ↓
Detect Duplicates
      ↓
Review Cases
      ↓
Approve / Reject / Edit
      ↓
Export Dataset
```

Optional second workflow:

```text
Approved Dataset
      ↓
Choose Model
      ↓
Run Evaluation
      ↓
Compare Model Answer vs Reference
      ↓
View Results Dashboard
```

---

# 7. MVP Features

## 7.1 Create Evaluation Project

User can create a project with:

- project name
- optional description
- creation date

Example:

```text
Project Name:
Employee Handbook Evaluation

Description:
Evaluation set for testing questions against our employee handbook.
```

---

## 7.2 Source Input

MVP supports:

- pasted text
- `.txt`
- `.md`
- text-based `.pdf`

Do not support scanned PDFs in MVP.

If a PDF contains no extractable text, display a clear message:

> This PDF appears to require OCR, which is not supported in the current version.

Stretch goal:

- webpage URL ingestion

---

# 8. Source Processing

The backend should:

1. extract text
2. normalize whitespace
3. remove obviously empty sections
4. split text into chunks
5. store source and chunk metadata

Recommended chunk size:

- approximately 500–1,000 words

Keep chunking simple.

Possible implementation:

- split by paragraphs
- accumulate paragraphs until target length
- preserve document order

Do not build a complicated semantic chunker for MVP.

---

# 9. Dataset Configuration

Before generating examples, allow the user to choose:

## Number of examples

- 10
- 25
- 50

Default:

```text
25
```

## Difficulty

- Easy
- Medium
- Mixed

Default:

```text
Mixed
```

## Test types

- Direct factual
- Multi-step
- Unanswerable

Default:

```text
All
```

## Model Selection

The generation settings should also include:

- provider
- model

For MVP:

```text
Provider: Gemini
Model: configured Gemini default
```

If multiple Gemini models are configured, the user may choose between them.

The interface should describe cheaper/free-tier-oriented models as:

```text
Budget / Fast
```

rather than promising that a particular model will always remain free.

Provider/model options should come from backend configuration rather than being duplicated across frontend components.

## Cost-Safe Development Defaults

To keep the project inexpensive while developing:

- default generation count to 10 during development
- never call the live API from unit tests
- mock all provider calls in automated tests
- require an explicit user action before starting a model evaluation
- show how many evaluation cases will be sent before a run begins
- execute requests sequentially or with very small concurrency
- do not automatically retry repeatedly
- allow a maximum generation/evaluation batch size through configuration
- log request counts, but never log API keys
- support a `MOCK` provider for local UI/backend development without API usage

Suggested configuration:

```text
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
MAX_GENERATION_CASES=50
MAX_EVALUATION_CASES=50
USE_MOCK_LLM=false
```

The application should remain usable for UI development with:

```text
USE_MOCK_LLM=true
```

This mode returns deterministic fixture responses and consumes no external API tokens.

---

# 10. Evaluation Case Schema

Each generated case should follow a strict schema.

Example:

```json
{
  "id": "eval_001",
  "question": "How many days of annual leave are employees entitled to?",
  "reference_answer": "Employees receive 25 days of annual leave per year.",
  "source_chunk_ids": ["chunk_004"],
  "category": "employee_benefits",
  "difficulty": "easy",
  "test_type": "direct",
  "is_answerable": true,
  "status": "generated"
}
```

Unanswerable example:

```json
{
  "id": "eval_002",
  "question": "Which gym membership provider does the company use?",
  "reference_answer": null,
  "source_chunk_ids": ["chunk_007"],
  "category": "employee_benefits",
  "difficulty": "medium",
  "test_type": "unanswerable",
  "is_answerable": false,
  "status": "generated"
}
```

Use Pydantic models to enforce the schema.

---

# 11. Supported Test Types

Keep the MVP to three test types.

## 11.1 Direct Factual

The answer can be found explicitly in one source chunk.

Example:

Source:

> Employees receive 25 days of annual leave each year.

Question:

> How many days of annual leave do employees receive?

Expected answer:

> 25 days.

---

## 11.2 Multi-Step

The answer requires combining two related facts.

Example:

Source:

> Employees receive 20 standard leave days. Employees with five years of service receive five additional days.

Question:

> How much annual leave does an employee with six years of service receive?

Expected answer:

> 25 days.

For MVP, multi-step questions should use no more than two source chunks.

---

## 11.3 Unanswerable

The source does not contain enough information to answer.

Example:

Question:

> Which gym membership company does the employer use?

Expected behavior:

> The model should say that the information is not provided.

Purpose:

- test hallucination resistance
- test whether the model acknowledges missing information

---

# 12. Difficulty Levels

Use simple definitions.

## Easy

- one explicit fact
- one source chunk
- little reasoning

## Medium

- paraphrasing required
- or two facts must be combined

## Hard

Not required in MVP.

May be added later.

---

# 13. Dataset Generation Pipeline

```text
Source Document
      |
      v
Text Extraction
      |
      v
Text Cleaning
      |
      v
Chunking
      |
      v
LLM Generation
      |
      v
Pydantic Validation
      |
      v
Duplicate Detection
      |
      v
Grounding Heuristic
      |
      v
Database Storage
      |
      v
Human Review
      |
      v
Export
```

---

# 14. LLM Generation

EvalForge should use an existing LLM through an API.

The LLM is responsible for generating candidate evaluation examples.

The application is responsible for:

- selecting source content
- constructing prompts
- validating model output
- rejecting malformed output
- checking duplicates
- storing results
- allowing manual review

Example generation instruction:

```text
You are generating evaluation examples for an AI system.

Use only the supplied source text.

Generate evaluation questions that test whether another AI model understands the source.

For answerable questions, provide a concise reference answer.

For unanswerable questions, do not invent an answer.

Return only valid structured JSON matching the requested schema.
```

---

# 15. Quality Validation

The project must contain validation logic so it is more than a simple LLM wrapper.

MVP requires four types of validation.

---

## 15.1 Schema Validation

Use Pydantic.

Check:

- question is non-empty
- test type is valid
- difficulty is valid
- source chunk IDs exist
- answerable questions contain reference answers
- unanswerable questions do not invent reference answers

Malformed examples should not enter the final dataset.

---

## 15.2 Semantic Duplicate Detection

Generate embeddings for each question.

Calculate cosine similarity between the new question and existing questions.

Suggested starting rule:

```text
similarity >= 0.90 → flag as probable duplicate
```

This threshold should exist as a constant/configuration value, not be scattered throughout the code.

The user may still manually keep a flagged example.

Do not use a dedicated vector database for MVP.

Possible storage:

- embedding array in PostgreSQL
- or regenerate embeddings when required for small datasets

For a student-scale dataset, either is acceptable.

---

## 15.3 Grounding Heuristic

For answerable examples, estimate whether the reference answer is related to the supplied source.

Simple implementation:

1. generate embedding for reference answer
2. generate embedding for source chunk
3. calculate cosine similarity
4. flag suspiciously low values

Important:

This is a heuristic, not a correctness guarantee.

The UI should describe it as:

```text
Grounding confidence
```

or:

```text
Grounding check
```

Do not claim the value proves factual correctness.

---

## 15.4 Basic Content Validation

Reject or flag:

- empty questions
- extremely long questions
- extremely long answers
- malformed JSON
- duplicate text
- missing source references
- invalid categories
- unsupported difficulty labels

---

# 16. Human Review

The user must be able to review generated examples.

Each example can be:

- Generated
- Approved
- Rejected

The user can:

- edit the question
- edit the reference answer
- approve the case
- reject the case
- see source text
- see duplicate warning
- see grounding warning

This is important because generated evaluation data should not be treated as automatically perfect.

---

# 17. Dataset Export

Export approved examples as:

## JSONL

Example:

```json
{"question":"How many leave days are provided?","reference_answer":"25 days","test_type":"direct"}
{"question":"What gym provider is used?","reference_answer":null,"test_type":"unanswerable"}
```

## CSV

Columns:

```text
id
question
reference_answer
category
difficulty
test_type
is_answerable
source_chunk_ids
```

JSONL should be the main format.

CSV is included because it is easy to inspect.

---

# 18. Simple Model Evaluation

Once the core generator is stable, implement model evaluation.

The user chooses:

- an approved dataset
- a configured LLM provider/model

For the MVP, Gemini must be available here. The same provider abstraction used for dataset generation should be reused for evaluation.

EvalForge then:

1. sends each question to the model
2. stores the model response
3. compares response with the reference
4. calculates a simple result
5. displays aggregate statistics

---

# 19. Evaluation Metrics

Keep evaluation understandable.

## 19.1 Answerable Questions

Use embedding similarity between:

- reference answer
- model answer

Example:

```text
cosine similarity >= configured threshold → semantic pass
```

This is a heuristic.

Do not claim it perfectly measures correctness.

---

## 19.2 Unanswerable Questions

Use a simple LLM-based or rule-based check to determine whether the response appropriately indicates missing information.

For the first implementation, an LLM judge is acceptable if clearly documented.

The evaluator prompt should return structured output such as:

```json
{
  "pass": true,
  "reason": "The model correctly stated that the source did not provide this information."
}
```

---

## 19.3 Aggregate Metrics

Dashboard should display:

- total evaluation cases
- passed
- failed
- pass rate
- direct factual pass rate
- multi-step pass rate
- unanswerable pass rate

Do not build advanced ML metrics that are not meaningful for this application.

---

# 20. Evaluation Result Schema

Example:

```json
{
  "evaluation_case_id": "eval_001",
  "model_name": "example-model",
  "model_response": "Employees receive 25 days.",
  "semantic_similarity": 0.94,
  "passed": true,
  "evaluation_reason": "Response closely matches reference answer."
}
```

---

# 21. Frontend Pages

Keep UI clean and minimal.

Required pages:

## 21.1 Home

Show:

- product name
- short explanation
- Create Project button
- recent projects

---

## 21.2 Project Page

Show:

- project name
- source files
- dataset statistics
- Generate Dataset button
- Export button
- Run Evaluation button

---

## 21.3 Source Page

Allow:

- upload file
- paste text
- preview extracted content
- show chunk count

---

## 21.4 Generation Page

Controls:

- number of questions
- difficulty
- test types
- provider
- model
- Generate button

Show progress.

---

## 21.5 Dataset Review Page

Use a table or card list.

Columns/details:

- question
- answer
- difficulty
- test type
- status
- duplicate warning
- grounding warning

Actions:

- Edit
- Approve
- Reject

---

## 21.6 Evaluation Page

Show:

- provider used
- model used
- total tests
- passed
- failed
- pass percentage
- breakdown by test type

Below summary:

- each question
- expected answer
- model answer
- pass/fail
- similarity score or judge reason

---

# 22. Suggested Technology Stack

Use technologies that are common, understandable, and portfolio-friendly.

## Frontend

```text
Next.js
TypeScript
React
Tailwind CSS
```

Optional component library:

```text
shadcn/ui
```

Do not add multiple UI frameworks.

---

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
```

---

## Database

```text
PostgreSQL
```

SQLite may be used for initial development if needed, but final local demo should support PostgreSQL.

---

## AI

Use a small provider abstraction so EvalForge is not tied to one LLM company.

### MVP provider priority

1. **Google Gemini — required and default**
2. Anthropic Claude — optional
3. OpenAI — optional

The project is being developed with Claude Code, but:

> **Claude Code is the development assistant, not the runtime architecture.**

Do not require an Anthropic API key just because Claude Code is being used to build the repository.

### Default low-cost development model

Use a configurable Gemini model.

Recommended starting default:

```text
gemini-3.1-flash-lite
```

A fallback configuration may use:

```text
gemini-2.5-flash-lite
```

Do not hard-code these model names throughout the application. Store the selected model in configuration and expose it through the provider layer so it can be changed when model availability changes.

Example environment configuration:

```text
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
```

The Google Gemini API key should be compatible with a key created through Google AI Studio.

### Provider interface

Example:

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):

    @abstractmethod
    def generate_eval_cases(self, ...):
        ...

    @abstractmethod
    def generate_response(self, ...):
        ...

    @abstractmethod
    def judge_response(self, ...):
        ...
```

Possible implementations:

```text
GeminiProvider       # required
AnthropicProvider    # stretch / optional
OpenAIProvider       # stretch / optional
```

Only `GeminiProvider` must be fully working for the MVP.

The UI and backend architecture should allow additional providers later without rewriting dataset generation or evaluation logic.

---

# 23. Embeddings

Use an existing embedding model.

Possible choices:

- OpenAI embedding API
- sentence-transformers locally

Preferred student-friendly option:

```text
sentence-transformers
```

Possible model:

```text
all-MiniLM-L6-v2
```

Why:

- small
- free to run locally
- easy to understand
- suitable for semantic similarity demonstrations

Claude Code should not introduce a hosted vector database unless required.

---

# 24. Recommended Repository Structure

Claude Code should follow a simple monorepo structure.

```text
evalforge/
│
├── README.md
├── .gitignore
├── .env.example
│
├── api/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   │
│   │   ├── api/
│   │   │   ├── projects.py
│   │   │   ├── sources.py
│   │   │   ├── datasets.py
│   │   │   └── evaluations.py
│   │   │
│   │   ├── models/
│   │   │   ├── project.py
│   │   │   ├── source.py
│   │   │   ├── eval_case.py
│   │   │   └── evaluation_result.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── project.py
│   │   │   ├── source.py
│   │   │   ├── eval_case.py
│   │   │   └── evaluation.py
│   │   │
│   │   ├── services/
│   │   │   ├── document_service.py
│   │   │   ├── chunking_service.py
│   │   │   ├── generation_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── validation_service.py
│   │   │   ├── evaluation_service.py
│   │   │   └── export_service.py
│   │   │
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   └── anthropic_provider.py
│   │   │
│   │   └── db/
│   │       ├── database.py
│   │       └── migrations/
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
└── web/
    ├── app/
    ├── components/
    ├── lib/
    ├── types/
    ├── package.json
    └── .env.example
```

Do not create extra layers unless they solve a real problem.

---

# 25. Database Entities

Use a small number of tables.

## Project

```text
id
name
description
created_at
```

## SourceDocument

```text
id
project_id
filename
source_type
raw_text
created_at
```

## SourceChunk

```text
id
source_document_id
chunk_index
text
```

## EvaluationCase

```text
id
project_id
question
reference_answer
category
difficulty
test_type
is_answerable
status
duplicate_score
grounding_score
created_at
```

## EvaluationCaseSource

Join table:

```text
evaluation_case_id
source_chunk_id
```

## EvaluationRun

```text
id
project_id
model_name
created_at
```

## EvaluationResult

```text
id
evaluation_run_id
evaluation_case_id
model_response
similarity_score
passed
reason
```

Avoid creating unnecessary tables.

---

# 26. API Endpoints

Example endpoints:

## Projects

```text
POST   /projects
GET    /projects
GET    /projects/{project_id}
DELETE /projects/{project_id}
```

## Sources

```text
POST /projects/{project_id}/sources
GET  /projects/{project_id}/sources
```

## Generation

```text
POST /projects/{project_id}/generate
```

## Evaluation Cases

```text
GET   /projects/{project_id}/cases
PATCH /cases/{case_id}
DELETE /cases/{case_id}
```

## Export

```text
GET /projects/{project_id}/export?format=jsonl
GET /projects/{project_id}/export?format=csv
```

## Evaluation Runs

```text
POST /projects/{project_id}/evaluations
GET  /projects/{project_id}/evaluations
GET  /evaluations/{evaluation_id}
```

---

# 27. Claude Code Development Rules

This section is specifically for building the project with Claude Code.

Claude Code should treat this PRD as the source of truth.

## Rule 1 — Build Incrementally

Do not attempt to implement the entire application in one generation.

Work milestone by milestone.

At the end of every milestone:

1. run tests
2. fix errors
3. summarize what was implemented
4. list files changed
5. confirm acceptance criteria
6. stop before beginning the next milestone unless explicitly instructed

---

## Rule 2 — Prefer Simple Code

Prefer:

- readable functions
- obvious variable names
- small services
- comments explaining non-obvious logic
- standard libraries where possible

Avoid:

- excessive abstractions
- complicated design patterns
- unnecessary dependency injection frameworks
- metaprogramming
- deeply nested inheritance
- premature optimization

The owner of this repository should be able to explain the code in a university interview.

---

## Rule 3 — Explain AI/ML Logic

Any file containing:

- embeddings
- cosine similarity
- generation prompts
- evaluation thresholds
- LLM judging

must contain comments explaining the logic in straightforward terms.

Example:

```python
# Cosine similarity measures how closely two vectors point
# in the same direction. Here we use it as a rough measure
# of semantic similarity between two pieces of text.
```

Do not hide important ML concepts behind unexplained utility functions.

---

## Rule 4 — Avoid Fake Complexity

Do not add features merely to make the project look advanced.

The project should be impressive because it works and can be explained.

---

## Rule 5 — Never Commit Secrets

API keys must be loaded from environment variables.

Required:

```text
.env
.env.example
```

`.env` must be excluded in `.gitignore`.

Never hard-code:

- Gemini API keys
- Anthropic/OpenAI API keys if those providers are later added
- passwords
- database credentials

The committed `.env.example` should include placeholders such as:

```text
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
USE_MOCK_LLM=false
```

---

## Rule 6 — Test as You Build

Every backend service should receive tests when practical.

Prioritize tests for:

- chunking
- schema validation
- duplicate detection
- cosine similarity
- dataset export
- evaluation scoring

Mock external LLM API calls in automated tests.

Tests should not consume paid API tokens.

---

## Rule 7 — Keep Provider Calls Isolated

External LLM calls should live in the provider/service layer.

Do not place Anthropic/OpenAI API code directly inside route handlers.

---

## Rule 8 — Preserve Student Ownership

Generated code should be understandable and maintainable by one student.

If a solution introduces a concept significantly beyond typical undergraduate software engineering without a clear need, prefer a simpler design.

---

# 28. Development Milestones

Claude Code should implement the project in the following order.

---

## M0 — Repository Setup

### Build

- repository structure
- FastAPI backend
- Next.js frontend
- environment files
- basic README
- database connection
- health endpoint

### Required endpoint

```text
GET /health
```

Expected:

```json
{
  "status": "ok"
}
```

### Acceptance Criteria

- backend starts
- frontend starts
- PostgreSQL connection works
- health endpoint returns 200
- secrets are not committed

---

# M1 — Projects

### Build

- Project database model
- Pydantic schemas
- create project
- list projects
- get project
- delete project
- simple frontend project list

### Acceptance Criteria

User can:

1. open app
2. create a project
3. see project in list
4. open project
5. delete project

---

# M2 — Source Ingestion

### Build

Support:

- pasted text
- `.txt`
- `.md`

Then add:

- text-based `.pdf`

Store extracted text.

### Acceptance Criteria

User can add source material and view extracted text.

PDF parsing must fail gracefully if no usable text exists.

---

# M3 — Chunking

### Build

- paragraph-based text chunker
- chunk database model
- source-to-chunk relationship
- tests

### Acceptance Criteria

Uploading a source creates ordered chunks.

Tests cover:

- empty input
- small input
- multi-paragraph input
- large input

---

# M4 — LLM Generation

### Build

- provider interface
- `GeminiProvider`
- Google AI Studio API-key configuration
- configurable Gemini model
- deterministic `MockProvider`
- generation prompt
- structured output
- Pydantic validation
- generation endpoint
- mocked provider tests

### Acceptance Criteria

Given source chunks, EvalForge can generate valid evaluation cases using Gemini.

The project can also run generation in mock mode without making an external API request.

Changing the configured Gemini model does not require changing generation-service code.

Malformed LLM output does not crash the application.

Automated tests do not consume Gemini API quota.

---

# M5 — Dataset Review

### Build

- case list
- edit case
- approve case
- reject case
- source preview

### Acceptance Criteria

User can manually review every generated case.

---

# M6 — Embeddings + Duplicate Detection

### Build

Use:

```text
sentence-transformers
all-MiniLM-L6-v2
```

Implement:

- text embeddings
- cosine similarity
- duplicate threshold
- duplicate warning

### Acceptance Criteria

Two highly similar generated questions are flagged.

Unit tests verify cosine similarity logic.

---

# M7 — Grounding Heuristic

### Build

Compare reference answer embedding to relevant source chunk embedding.

Store:

```text
grounding_score
```

Flag low-scoring examples.

### Acceptance Criteria

UI displays:

```text
Grounding OK
```

or:

```text
Review grounding
```

Do not label this as factual certainty.

---

# M8 — Dataset Export

### Build

- JSONL export
- CSV export
- export only approved cases by default

### Acceptance Criteria

User can download valid JSONL and CSV datasets.

Automated tests verify export formatting.

---

# M9 — Model Evaluation

### Build

- choose configured provider/model
- Gemini evaluation support
- show evaluation case count before execution
- run questions
- store responses
- calculate semantic similarity
- evaluate unanswerable cases
- save result
- mock external calls in automated tests

### Acceptance Criteria

An approved dataset can be run through Gemini and produces persistent evaluation results.

The selected provider and exact model identifier are saved with the evaluation run.

Automated tests do not consume live Gemini API quota.

---

# M10 — Results Dashboard

### Build

Display:

- total cases
- passed
- failed
- pass rate
- breakdown by test type

Show individual results.

### Acceptance Criteria

User can inspect both aggregate results and specific model failures.

---

# M11 — Testing + Documentation

### Build

- backend unit tests
- API tests
- frontend critical-path tests where practical
- README
- architecture diagram
- sample dataset
- demo instructions

### README must explain

1. problem
2. architecture
3. tech stack
4. setup
5. how dataset generation works
6. how embeddings are used
7. limitations
8. future improvements

---

# 29. Testing Requirements

Minimum target:

```text
25+ meaningful backend tests
```

Do not create useless tests purely to inflate test count.

Important test areas:

- text chunking
- schema validation
- duplicate similarity
- grounding scoring
- project CRUD
- export
- model evaluation logic

External APIs should be mocked.

---

# 30. Demo Scenario

Use one strong demo dataset.

Recommended source:

```text
fictional employee handbook
```

Why:

- understandable
- contains policies
- supports direct questions
- supports multi-step questions
- easy to create unanswerable cases
- avoids complicated domain expertise

Suggested demo:

1. upload handbook
2. generate 25 evaluation cases
3. show direct/multi-step/unanswerable examples
4. show duplicate detection
5. reject one weak example
6. edit one example
7. approve dataset
8. export JSONL
9. run model evaluation
10. show pass-rate dashboard
11. inspect one failure

This should make a strong 2–4 minute portfolio demo.

---

# 31. Example Dataset Generation Prompt

Claude Code may improve wording, but preserve the intent.

```text
You are generating evaluation cases for an AI system.

SOURCE:
{source_text}

Generate {count} evaluation cases.

Allowed test types:
- direct
- multi_step
- unanswerable

Rules:

1. Answerable questions must be supported by the supplied source.
2. Do not use outside knowledge.
3. Reference answers must be concise.
4. Unanswerable questions must ask for information not contained in the source.
5. Avoid duplicate questions.
6. Use clear language.
7. Return only valid JSON.
8. Match the supplied schema exactly.
```

---

# 32. Example Evaluation Prompt

For cases that need an LLM judge:

```text
You are evaluating an AI response.

QUESTION:
{question}

REFERENCE ANSWER:
{reference_answer}

MODEL RESPONSE:
{model_response}

Determine whether the model response correctly answers the question.

Return JSON:

{
  "pass": true | false,
  "reason": "short explanation"
}
```

Use this only where simpler deterministic checks are insufficient.

---

# 33. Gemini Free-Tier and Cost Considerations

The project should be designed so a student can build and demo it using inexpensive API access.

Gemini is the recommended MVP provider because Google offers free-tier access to eligible Gemini API models, subject to Google's current rate limits and terms.

Important design rule:

> Never assume that a specific model, quota, or price will remain free forever.

Therefore:

- model identifiers belong in configuration
- model choices should be replaceable
- the UI should not permanently label a model as "free"
- README documentation should link users to the current provider pricing/rate-limit documentation
- live-provider tests must be optional
- unit/integration tests should use mocks
- demo datasets should be small

### Free-tier data note

When using a free API tier, users should avoid uploading private, confidential, regulated, or otherwise sensitive source documents unless they have reviewed and accepted the provider's current data-use terms.

For the included demo, use fictional or public data.

---

# 34. Error Handling

The app should handle common errors clearly.

Examples:

## Invalid file

```text
Unsupported file type.
```

## Empty PDF

```text
No extractable text was found in this PDF.
```

## LLM API failure

```text
Generation failed. Please try again.
```

Log the underlying technical error server-side.

## Invalid LLM JSON

Attempt one controlled retry.

If second attempt fails:

- skip that batch
- show error
- do not silently store malformed data

---

# 35. Logging

Use standard Python logging.

Log:

- generation requests
- parsing failures
- validation failures
- API errors
- evaluation runs

Do not log:

- API keys
- passwords
- full secrets

Avoid building complex observability infrastructure.

---

# 36. Performance Expectations

Student-scale targets:

- source documents under ~100 pages
- datasets up to 50 generated cases per run
- one user locally
- one model evaluation at a time

The project does not need to support thousands of concurrent users.

---

# 37. Security Expectations

MVP:

- environment variables
- input validation
- file type validation
- reasonable upload size limits
- safe filenames
- no arbitrary code execution

Authentication is not required for local portfolio demo.

---

# 38. UI Style

Aim for:

- modern
- clean
- developer-tool aesthetic
- simple typography
- minimal animations
- strong information hierarchy

Avoid:

- excessive gradients
- glassmorphism everywhere
- complicated dashboards
- fake enterprise UI
- unnecessary animation libraries

The application should feel polished but believable.

---

# 39. Suggested Dashboard Summary

Example:

```text
Employee Handbook Evaluation

Sources: 1
Chunks: 42
Generated Cases: 25
Approved: 21
Rejected: 4

Test Type Breakdown
Direct: 10
Multi-Step: 8
Unanswerable: 7

Latest Evaluation
Model: Claude
Pass Rate: 84%
```

---

# 40. Stretch Goals

Only begin stretch goals after M0–M11 are complete.

Possible additions:

- URL ingestion
- hard difficulty
- custom generation instructions
- multiple LLM providers
- comparison between two models
- downloadable evaluation report
- richer charts
- Hugging Face dataset export
- configurable similarity threshold
- batch dataset regeneration
- category filtering
- question search
- source citations in exports

---

# 41. Features That Should Stay Stretch Goals

Do not let Claude Code introduce these early:

- pgvector
- Pinecone
- Weaviate
- Kubernetes
- Docker Swarm
- message queues
- Celery
- Redis
- LangChain unless a clear need appears
- LlamaIndex unless a clear need appears
- agent frameworks
- advanced RAG
- custom fine-tuning
- cloud deployment automation
- OAuth
- complex dashboards

A simple implementation is preferred.

---

# 42. Educational Knowledge Requirements

The developer should be able to explain the following before calling the project complete.

## Embeddings

Understand:

- text converted into vectors
- semantically similar text produces similar vectors
- embeddings do not directly mean "correctness"

## Cosine Similarity

Understand:

```text
cosine similarity = (A · B) / (||A|| ||B||)
```

High-level meaning:

- close to 1 → vectors point in similar directions
- lower values → less similar

## Structured Outputs

Understand why Pydantic/schema validation is needed when consuming LLM output.

## Synthetic Data

Understand:

- generated datasets may contain errors
- human review matters
- synthetic evaluation data is useful but imperfect

## LLM-as-Judge

Understand:

- another model can assess answers
- judgments can be inconsistent
- it should not be treated as absolute truth

## Hallucinations

Understand why unanswerable questions help test whether a model invents unsupported information.

---

# 43. CV Positioning

Once complete, an appropriate CV entry could look like:

### EvalForge — Automated LLM Evaluation Dataset Generator

Built a full-stack AI evaluation tool that converts source documents into structured LLM test datasets. Implemented automated question generation, semantic duplicate detection using MiniLM embeddings and cosine similarity, source-grounding heuristics, human review workflows, JSONL/CSV export, and model performance evaluation through a FastAPI, PostgreSQL, and Next.js stack.

Do not include metrics until actually measured.

Later, real measurements can be added, for example:

```text
Generated and validated 500+ evaluation cases across direct,
multi-step, and unanswerable question types.
```

Only claim numbers that have actually been produced.

---

# 44. Portfolio Value

This project should demonstrate five clear competencies:

## Software Engineering

- full-stack application
- REST APIs
- database design
- testing
- maintainable structure

## AI Engineering

- LLM integration
- structured generation
- evaluation workflows

## ML Fundamentals

- embeddings
- cosine similarity
- semantic comparison

## Data Engineering

- document processing
- chunking
- validation
- dataset generation
- export

## Product Thinking

- clear user workflow
- human review
- meaningful limitations
- practical application

---

# 45. Definition of Done

The project is complete when:

- user can create a project
- user can upload supported source material
- text is extracted and chunked
- application generates structured evaluation cases using Gemini
- Gemini model is configurable through environment settings
- mock LLM mode works without external API usage
- Pydantic validates generated cases
- duplicate questions are detected semantically
- answer grounding is heuristically checked
- user can edit/approve/reject cases
- approved cases export to JSONL and CSV
- one LLM can be evaluated against the dataset
- results dashboard shows pass/fail statistics
- automated tests pass
- README explains the system
- API keys are not committed
- demo scenario works from start to finish

---

# 46. Final Claude Code Instruction

When using this document with Claude Code, give Claude the following operating instruction:

```text
Treat PRD.md as the source of truth.

Build only the milestone I explicitly request.

Before coding, inspect the existing repository so you do not duplicate
working functionality.

Prefer the simplest implementation that satisfies the acceptance criteria.

Do not introduce features listed as out of scope or stretch goals unless
I explicitly request them.

Use Gemini as the required MVP runtime LLM provider. Keep its API key and
model identifier in environment configuration. Do not require Anthropic or
OpenAI credentials for the core application.

Keep the code understandable for a third-year Computer Science student.
Add clear comments around embeddings, cosine similarity, LLM prompts,
validation logic, and evaluation decisions.

After implementing a milestone:

1. run the relevant tests
2. fix failures
3. summarize what changed
4. list files added or modified
5. explain any important design decisions
6. state whether every acceptance criterion passed
7. stop and wait for the next milestone
```

---

# 47. Recommended Build Order

Use this sequence with Claude Code:

```text
M0  Repository Setup
M1  Projects
M2  Source Ingestion
M3  Chunking
M4  LLM Generation
M5  Dataset Review
M6  Embeddings + Duplicate Detection
M7  Grounding Heuristic
M8  Export
M9  Model Evaluation
M10 Results Dashboard
M11 Testing + Documentation
```

Do not skip ahead simply because a later feature seems more interesting.

The goal is to finish a small, working, understandable system rather than create a large unfinished one.
