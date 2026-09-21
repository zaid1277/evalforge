"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ApiError,
  getEvaluation,
  getEvaluationDashboard,
  type EvaluationDashboard,
  type EvaluationRun,
} from "@/lib/api";
import PerformanceBreakdown from "./PerformanceBreakdown";
import ResultsTable, { ResultCard } from "./ResultsTable";
import SummaryCards from "./SummaryCards";

export default function EvaluationDetailPage() {
  const params = useParams<{ id: string }>();
  const evaluationId = Number(params.id);
  const invalidId = Number.isNaN(evaluationId);

  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [dashboard, setDashboard] = useState<EvaluationDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!invalidId);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    Promise.all([getEvaluation(evaluationId), getEvaluationDashboard(evaluationId)])
      .then(([runData, dashboardData]) => {
        if (cancelled) return;
        setRun(runData);
        setDashboard(dashboardData);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? "Evaluation run not found."
            : "Unable to load evaluation results."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [evaluationId, invalidId]);

  const displayError = invalidId ? "Evaluation run not found." : error;
  const failedResults = run?.results.filter((result) => !result.passed) ?? [];

  return (
    <main className="mx-auto flex max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <Link
        href={run ? `/projects/${run.project_id}` : "/"}
        className="text-sm text-neutral-500 hover:underline dark:text-neutral-400"
      >
        ← Back to project
      </Link>

      {loading && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Loading evaluation results...
        </p>
      )}

      {!loading && displayError && (
        <p className="text-sm text-red-600 dark:text-red-400">{displayError}</p>
      )}

      {!loading && !displayError && run && dashboard && (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Evaluation Run #{run.id}</h1>
          </header>

          <SummaryCards dashboard={dashboard} />

          <PerformanceBreakdown
            byTestType={dashboard.by_test_type}
            byDifficulty={dashboard.by_difficulty}
            byAnswerability={dashboard.by_answerability}
          />

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
              Failed Cases ({failedResults.length})
            </h2>
            {failedResults.length === 0 ? (
              <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                No failed cases in this run.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {failedResults.map((result) => (
                  <ResultCard key={result.id} result={result} defaultExpanded />
                ))}
              </ul>
            )}
          </section>

          <ResultsTable results={run.results} />
        </>
      )}
    </main>
  );
}
