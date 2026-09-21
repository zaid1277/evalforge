"use client";

import { useState } from "react";
import type { EvaluationResult } from "@/lib/api";

type PassFilter = "all" | "passed" | "failed";
type TestTypeFilter = "all" | "direct" | "multi_step" | "unanswerable";

const PASS_FILTERS: { value: PassFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
];

const TEST_TYPE_FILTERS: { value: TestTypeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "direct", label: "Direct" },
  { value: "multi_step", label: "Multi-Step" },
  { value: "unanswerable", label: "Unanswerable" },
];

export function ResultCard({
  result,
  defaultExpanded = false,
}: {
  result: EvaluationResult;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <li className="flex flex-col gap-2 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <div className="flex items-start justify-between gap-4">
        <span className="font-medium">{result.question}</span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
            result.passed
              ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
              : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
          }`}
        >
          {result.passed ? "Pass" : "Fail"}
        </span>
      </div>

      <span className="text-xs text-neutral-500 dark:text-neutral-400">
        {result.test_type} · {result.difficulty} · Semantic similarity:{" "}
        {result.semantic_similarity === null
          ? "N/A"
          : `${Math.round(result.semantic_similarity * 100)}%`}
      </span>

      {!defaultExpanded && (
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="self-start text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          {expanded ? "Hide details" : "Show details"}
        </button>
      )}

      {(expanded || defaultExpanded) && (
        <div className="flex flex-col gap-2 border-t border-neutral-200 pt-2 text-sm dark:border-neutral-800">
          <span className="text-neutral-600 dark:text-neutral-400">
            Reference answer: {result.reference_answer ?? "Not applicable (unanswerable)"}
          </span>
          <span className="text-neutral-600 dark:text-neutral-400">
            Model response: {result.model_response}
          </span>
          <span className="text-neutral-600 dark:text-neutral-400">
            Reason: {result.evaluation_reason}
          </span>
        </div>
      )}
    </li>
  );
}

export default function ResultsTable({ results }: { results: EvaluationResult[] }) {
  const [passFilter, setPassFilter] = useState<PassFilter>("all");
  const [testTypeFilter, setTestTypeFilter] = useState<TestTypeFilter>("all");

  // Results already arrive in deterministic EvaluationResult.id order
  // (see api/app/schemas/evaluation.py) -- filtering narrows the list
  // without ever reordering it.
  const filtered = results.filter((result) => {
    if (passFilter === "passed" && !result.passed) return false;
    if (passFilter === "failed" && result.passed) return false;
    if (testTypeFilter !== "all" && result.test_type !== testTypeFilter) return false;
    return true;
  });

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
        All Results ({results.length})
      </h2>

      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Filter by pass/fail status</legend>
        <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">Status:</span>
        {PASS_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={passFilter === value}
            onClick={() => setPassFilter(value)}
            className={`rounded-md px-3 py-1 text-sm font-medium ${
              passFilter === value
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
            }`}
          >
            {label}
          </button>
        ))}
      </fieldset>

      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Filter by test type</legend>
        <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
          Test type:
        </span>
        {TEST_TYPE_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={testTypeFilter === value}
            onClick={() => setTestTypeFilter(value)}
            className={`rounded-md px-3 py-1 text-sm font-medium ${
              testTypeFilter === value
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
            }`}
          >
            {label}
          </button>
        ))}
      </fieldset>

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Showing {filtered.length} of {results.length} results
      </p>

      {filtered.length === 0 ? (
        <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No results match this filter.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {filtered.map((result) => (
            <ResultCard key={result.id} result={result} />
          ))}
        </ul>
      )}
    </section>
  );
}
