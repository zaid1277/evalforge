import Link from "next/link";
import { formatPercent } from "@/lib/format";
import type { EvaluationDashboard } from "@/lib/api";

export default function SummaryCards({ dashboard }: { dashboard: EvaluationDashboard }) {
  const passRatePercent = dashboard.pass_rate === null ? 0 : Math.round(dashboard.pass_rate * 100);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCard label="Total Cases" value={String(dashboard.total_cases)} />
        <SummaryCard label="Passed" value={String(dashboard.passed_cases)} />
        <SummaryCard label="Failed" value={String(dashboard.failed_cases)} />
        <SummaryCard label="Pass Rate" value={formatPercent(dashboard.pass_rate)} />
      </div>

      <div className="flex flex-col gap-1">
        <div
          className="h-3 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800"
          role="progressbar"
          aria-valuenow={passRatePercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Overall pass rate"
        >
          <div
            className="h-full bg-neutral-900 dark:bg-neutral-100"
            style={{ width: `${passRatePercent}%` }}
          />
        </div>
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          Overall pass rate: {formatPercent(dashboard.pass_rate)}
        </span>
      </div>

      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Provider: {dashboard.provider} · Model: {dashboard.model_name} · Date:{" "}
        {new Date(dashboard.created_at).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        })}{" "}
        ·{" "}
        <Link
          href={`/projects/${dashboard.project_id}`}
          className="underline-offset-4 hover:underline"
        >
          Project #{dashboard.project_id}
        </Link>
      </p>

      <p className="rounded-md border border-neutral-200 bg-neutral-50 px-4 py-3 text-xs text-neutral-500 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
        Answerable cases are scored using semantic similarity, which is a heuristic and may not
        detect factual differences such as changed numbers. Unanswerable cases use a separate
        response-behavior judge. Pass/Fail reflects a heuristic evaluation result, not an absolute
        or objective correctness guarantee.
      </p>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">{label}</span>
      <span className="text-xl font-semibold tracking-tight">{value}</span>
    </div>
  );
}
