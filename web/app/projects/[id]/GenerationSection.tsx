"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  generateEvaluationCases,
  getEvaluationCaseSources,
  updateEvaluationCase,
  type EvaluationCase,
  type EvaluationCaseUpdate,
  type EvaluationStatus,
  type GenerationDifficulty,
  type SourceChunk,
  type TestType,
} from "@/lib/api";

const ALL_TEST_TYPES: { value: TestType; label: string }[] = [
  { value: "direct", label: "Direct" },
  { value: "multi_step", label: "Multi-Step" },
  { value: "unanswerable", label: "Unanswerable" },
];

const STATUS_FILTERS: { value: "all" | EvaluationStatus; label: string }[] = [
  { value: "all", label: "All" },
  { value: "generated", label: "Generated" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

export default function GenerationSection({
  projectId,
  cases,
  loadError,
  reload,
  onCaseUpdated,
}: {
  projectId: number;
  cases: EvaluationCase[] | null;
  loadError: string | null;
  reload: () => void;
  onCaseUpdated: (updated: EvaluationCase) => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | EvaluationStatus>("all");

  const counts = {
    total: cases?.length ?? 0,
    generated: cases?.filter((c) => c.status === "generated").length ?? 0,
    approved: cases?.filter((c) => c.status === "approved").length ?? 0,
    rejected: cases?.filter((c) => c.status === "rejected").length ?? 0,
  };

  const filteredCases =
    cases?.filter((c) => statusFilter === "all" || c.status === statusFilter) ?? null;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
          Evaluation Cases{cases ? ` (${cases.length})` : ""}
        </h2>
        <button
          type="button"
          onClick={() => setShowForm((current) => !current)}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
        >
          {showForm ? "Cancel" : "Generate Evaluation Dataset"}
        </button>
      </div>

      {showForm && (
        <GenerationForm
          projectId={projectId}
          onGenerated={() => {
            reload();
          }}
        />
      )}

      {loadError && <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>}

      {!loadError && cases === null && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Loading evaluation cases...
        </p>
      )}

      {!loadError && cases !== null && cases.length === 0 && (
        <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No evaluation cases yet.
        </p>
      )}

      {cases && cases.length > 0 && (
        <>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Total: {counts.total} · Generated: {counts.generated} · Approved: {counts.approved} ·
            Rejected: {counts.rejected}
          </p>

          <div className="flex gap-2">
            {STATUS_FILTERS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatusFilter(value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  statusFilter === value
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <ul className="flex flex-col gap-2">
            {filteredCases?.map((evalCase) => (
              <CaseCard key={evalCase.id} evalCase={evalCase} onUpdated={onCaseUpdated} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: EvaluationStatus }) {
  const styles: Record<EvaluationStatus, string> = {
    generated: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
    approved: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    rejected: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  };
  const labels: Record<EvaluationStatus, string> = {
    generated: "Generated",
    approved: "Approved",
    rejected: "Rejected",
  };

  return (
    <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

function CaseCard({
  evalCase,
  onUpdated,
}: {
  evalCase: EvaluationCase;
  onUpdated: (updated: EvaluationCase) => void;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [editing, setEditing] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleStatusChange(status: "approved" | "rejected") {
    setActionError(null);
    setStatusUpdating(true);
    try {
      const updated = await updateEvaluationCase(evalCase.id, { status });
      onUpdated(updated);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Unable to update status.");
    } finally {
      setStatusUpdating(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <div className="flex items-start justify-between gap-4">
        <span className="font-medium">{evalCase.question}</span>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {evalCase.needs_grounding_review && (
            <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800 dark:bg-orange-900/40 dark:text-orange-300">
              Review grounding · {Math.round((evalCase.grounding_score ?? 0) * 100)}%
            </span>
          )}
          {evalCase.is_possible_duplicate && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Possible duplicate · {Math.round((evalCase.duplicate_score ?? 0) * 100)}%
            </span>
          )}
          <StatusBadge status={evalCase.status} />
        </div>
      </div>

      <span className="text-sm text-neutral-600 dark:text-neutral-400">
        Reference answer: {evalCase.reference_answer ?? "Not provided"}
      </span>

      <span className="text-xs text-neutral-500 dark:text-neutral-400">
        {evalCase.category} · {evalCase.difficulty} · {evalCase.test_type} · Source chunks:{" "}
        {evalCase.source_chunk_ids.join(", ")}
        {!evalCase.is_possible_duplicate && evalCase.duplicate_score !== null && (
          <> · Duplicate similarity: {Math.round(evalCase.duplicate_score * 100)}%</>
        )}
        {evalCase.grounding_score === null ? (
          <> · Grounding: Not applicable</>
        ) : (
          !evalCase.needs_grounding_review && (
            <> · Grounding check: OK · {Math.round(evalCase.grounding_score * 100)}%</>
          )
        )}
      </span>

      {actionError && <p className="text-sm text-red-600 dark:text-red-400">{actionError}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setShowEvidence((current) => !current)}
          className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          {showEvidence ? "Hide Evidence" : "View Evidence"}
        </button>
        <button
          type="button"
          onClick={() => setEditing((current) => !current)}
          className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          {editing ? "Cancel Edit" : "Edit"}
        </button>
        {evalCase.status !== "approved" && (
          <button
            type="button"
            disabled={statusUpdating}
            onClick={() => handleStatusChange("approved")}
            className="text-sm font-medium text-green-700 underline-offset-4 hover:underline disabled:opacity-50 dark:text-green-400"
          >
            Approve
          </button>
        )}
        {evalCase.status !== "rejected" && (
          <button
            type="button"
            disabled={statusUpdating}
            onClick={() => handleStatusChange("rejected")}
            className="text-sm font-medium text-red-600 underline-offset-4 hover:underline disabled:opacity-50 dark:text-red-400"
          >
            Reject
          </button>
        )}
      </div>

      {showEvidence && <EvidencePanel caseId={evalCase.id} />}

      {editing && (
        <EditForm
          evalCase={evalCase}
          onSaved={(updated) => {
            onUpdated(updated);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </li>
  );
}

function EvidencePanel({ caseId }: { caseId: number }) {
  const [chunks, setChunks] = useState<SourceChunk[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvaluationCaseSources(caseId)
      .then(setChunks)
      .catch(() => setError("Unable to load source evidence."));
  }, [caseId]);

  return (
    <div className="flex flex-col gap-3 rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-900">
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!error && chunks === null && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading evidence...</p>
      )}

      {chunks && chunks.length === 0 && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          No linked source evidence.
        </p>
      )}

      {chunks?.map((chunk) => (
        <div key={chunk.id} className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
            Chunk {chunk.chunk_index + 1} · Source: {chunk.source_filename} ·{" "}
            {chunk.word_count.toLocaleString()} words
          </span>
          <p className="whitespace-pre-wrap text-sm text-neutral-700 dark:text-neutral-300">
            {chunk.text}
          </p>
        </div>
      ))}
    </div>
  );
}

function EditForm({
  evalCase,
  onSaved,
  onCancel,
}: {
  evalCase: EvaluationCase;
  onSaved: (updated: EvaluationCase) => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState(evalCase.question);
  const [referenceAnswer, setReferenceAnswer] = useState(evalCase.reference_answer ?? "");
  const [category, setCategory] = useState(evalCase.category);
  const [difficulty, setDifficulty] = useState(evalCase.difficulty);
  const [testType, setTestType] = useState<TestType>(evalCase.test_type);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // is_answerable is fully determined by test_type (unanswerable cases can
  // never have a reference answer, and vice versa) -- rather than exposing
  // a separate control that could contradict test_type, the UI derives it
  // directly, so it can never send a knowingly contradictory combination.
  const unanswerable = testType === "unanswerable";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!question.trim()) {
      setError("Question is required.");
      return;
    }
    if (!category.trim()) {
      setError("Category is required.");
      return;
    }
    if (!unanswerable && !referenceAnswer.trim()) {
      setError("Reference answer is required for answerable cases.");
      return;
    }

    setSaving(true);
    try {
      const patch: EvaluationCaseUpdate = {
        question: question.trim(),
        category: category.trim(),
        difficulty,
        test_type: testType,
        is_answerable: !unanswerable,
        reference_answer: unanswerable ? null : referenceAnswer.trim(),
      };
      const updated = await updateEvaluationCase(evalCase.id, patch);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor={`edit-question-${evalCase.id}`} className="text-xs font-medium">
          Question
        </label>
        <textarea
          id={`edit-question-${evalCase.id}`}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={2}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor={`edit-category-${evalCase.id}`} className="text-xs font-medium">
          Category
        </label>
        <input
          id={`edit-category-${evalCase.id}`}
          type="text"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <div className="flex gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor={`edit-difficulty-${evalCase.id}`} className="text-xs font-medium">
            Difficulty
          </label>
          <select
            id={`edit-difficulty-${evalCase.id}`}
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value as "easy" | "medium")}
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          >
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={`edit-test-type-${evalCase.id}`} className="text-xs font-medium">
            Test Type
          </label>
          <select
            id={`edit-test-type-${evalCase.id}`}
            value={testType}
            onChange={(event) => setTestType(event.target.value as TestType)}
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          >
            {ALL_TEST_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium">Reference Answer</label>
        {unanswerable ? (
          <p className="text-sm italic text-neutral-500 dark:text-neutral-400">
            Not provided (unanswerable case)
          </p>
        ) : (
          <textarea
            value={referenceAnswer}
            onChange={(event) => setReferenceAnswer(event.target.value)}
            rows={2}
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          />
        )}
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function GenerationForm({
  projectId,
  onGenerated,
}: {
  projectId: number;
  onGenerated: () => void;
}) {
  const [count, setCount] = useState(10);
  const [difficulty, setDifficulty] = useState<GenerationDifficulty>("mixed");
  const [testTypes, setTestTypes] = useState<TestType[]>(["direct", "multi_step", "unanswerable"]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function toggleTestType(value: TestType) {
    setTestTypes((current) =>
      current.includes(value) ? current.filter((t) => t !== value) : [...current, value]
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (testTypes.length === 0) {
      setError("Select at least one test type.");
      return;
    }
    if (!Number.isInteger(count) || count <= 0) {
      setError("Number of cases must be a positive whole number.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await generateEvaluationCases(projectId, { count, difficulty, test_types: testTypes });
      setSuccessMessage(
        `Generated ${result.generated_count} evaluation case${result.generated_count === 1 ? "" : "s"} using ${result.provider} (${result.model}).`
      );
      onGenerated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to generate evaluation cases.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-md border border-neutral-200 p-4 dark:border-neutral-800"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="gen-count" className="text-sm font-medium">
          Number of cases
        </label>
        <input
          id="gen-count"
          type="number"
          min={1}
          value={count}
          onChange={(event) => setCount(Number(event.target.value))}
          className="w-32 rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="gen-difficulty" className="text-sm font-medium">
          Difficulty
        </label>
        <select
          id="gen-difficulty"
          value={difficulty}
          onChange={(event) => setDifficulty(event.target.value as GenerationDifficulty)}
          className="w-40 rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="mixed">Mixed</option>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
        </select>
      </div>

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">Test types</legend>
        {ALL_TEST_TYPES.map(({ value, label }) => (
          <label key={value} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={testTypes.includes(value)}
              onChange={() => toggleTestType(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {successMessage && (
        <p className="text-sm text-green-600 dark:text-green-400">{successMessage}</p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {submitting ? "Generating..." : "Generate"}
      </button>
    </form>
  );
}
