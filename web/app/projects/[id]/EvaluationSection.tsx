"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  getEvaluations,
  getPublicConfig,
  runEvaluation,
  type EvaluationCase,
  type EvaluationRun,
  type EvaluationRunSummary,
  type PublicConfig,
} from "@/lib/api";
import { formatPercent } from "@/lib/format";

function passRate(run: { passed_cases: number; total_cases: number }): number | null {
  return run.total_cases > 0 ? run.passed_cases / run.total_cases : null;
}

export default function EvaluationSection({
  projectId,
  cases,
}: {
  projectId: number;
  cases: EvaluationCase[] | null;
}) {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [runs, setRuns] = useState<EvaluationRunSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastCompletedRun, setLastCompletedRun] = useState<EvaluationRun | null>(null);

  useEffect(() => {
    getPublicConfig()
      .then(setConfig)
      .catch(() => setLoadError((current) => current ?? "Unable to load provider configuration."));
  }, []);

  function reloadRuns() {
    getEvaluations(projectId)
      .then(setRuns)
      .catch(() => setLoadError((current) => current ?? "Unable to load previous evaluations."));
  }

  useEffect(reloadRuns, [projectId]);

  // Reuses the case list the page already loaded for the Evaluation
  // Cases section -- no extra API call just to show this count.
  const approvedCount = cases?.filter((c) => c.status === "approved").length ?? null;

  async function handleRun() {
    setRunError(null);
    setLastCompletedRun(null);
    setRunning(true);
    try {
      const run = await runEvaluation(projectId);
      setLastCompletedRun(run);
      reloadRuns();
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Unable to run evaluation.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
        Model Evaluation
      </h2>

      {loadError && <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>}

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Approved cases: {approvedCount ?? "..."} · Provider:{" "}
        {config ? (config.mock_mode ? "Mock" : config.provider) : "..."}
        {config && !config.mock_mode && <> · Model: {config.model}</>}
      </p>

      {approvedCount !== null && approvedCount > 0 && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          This will evaluate {approvedCount} approved case{approvedCount === 1 ? "" : "s"}.
        </p>
      )}

      <button
        type="button"
        onClick={handleRun}
        disabled={running || !approvedCount}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {running ? "Running evaluation..." : "Run Evaluation"}
      </button>

      {runError && <p className="text-sm text-red-600 dark:text-red-400">{runError}</p>}

      {lastCompletedRun && (
        <div className="flex flex-col gap-1 rounded-md border border-neutral-200 bg-neutral-50 p-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
          <p className="font-medium">Evaluation complete</p>
          <p className="text-neutral-600 dark:text-neutral-400">
            Total: {lastCompletedRun.total_cases} · Passed: {lastCompletedRun.passed_cases} ·
            Failed: {lastCompletedRun.failed_cases}
          </p>
          <Link
            href={`/evaluations/${lastCompletedRun.id}`}
            className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
          >
            View results
          </Link>
        </div>
      )}

      {runs && runs.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-neutral-200 bg-neutral-50 p-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
          <p className="font-medium">Latest Evaluation</p>
          <p className="text-neutral-600 dark:text-neutral-400">
            Model: {runs[0].model_name} · Pass rate: {formatPercent(passRate(runs[0]))} · Date:{" "}
            {new Date(runs[0].created_at).toLocaleDateString()}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h3 className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
          Previous Evaluations
        </h3>

        {runs !== null && runs.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No evaluations yet.</p>
        )}

        {runs && runs.length > 0 && (
          <ul className="flex flex-col gap-2">
            {runs.map((run) => (
              <li
                key={run.id}
                className="flex items-center justify-between gap-4 rounded-md border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
              >
                <div className="flex flex-col gap-0.5">
                  <span>
                    {new Date(run.created_at).toLocaleDateString()} · {run.provider} (
                    {run.model_name})
                  </span>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400">
                    {run.total_cases} case{run.total_cases === 1 ? "" : "s"} ·{" "}
                    {formatPercent(passRate(run))} pass rate · {run.passed_cases} passed /{" "}
                    {run.failed_cases} failed
                  </span>
                </div>
                <Link
                  href={`/evaluations/${run.id}`}
                  className="shrink-0 text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
                >
                  View Results
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
