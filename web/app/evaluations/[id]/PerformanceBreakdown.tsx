import { formatPercent } from "@/lib/format";
import type { MetricBreakdown } from "@/lib/api";

const TEST_TYPE_LABELS: Record<string, string> = {
  direct: "Direct",
  multi_step: "Multi-Step",
  unanswerable: "Unanswerable",
};
const TEST_TYPE_ORDER = ["direct", "multi_step", "unanswerable"];

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "Easy",
  medium: "Medium",
};
const DIFFICULTY_ORDER = ["easy", "medium"];

const ANSWERABILITY_LABELS: Record<string, string> = {
  answerable: "Answerable",
  unanswerable: "Unanswerable",
};
const ANSWERABILITY_ORDER = ["answerable", "unanswerable"];

export default function PerformanceBreakdown({
  byTestType,
  byDifficulty,
  byAnswerability,
}: {
  byTestType: Record<string, MetricBreakdown>;
  byDifficulty: Record<string, MetricBreakdown>;
  byAnswerability: Record<string, MetricBreakdown>;
}) {
  return (
    <div className="flex flex-col gap-6">
      <BreakdownGroup
        title="Breakdown by Test Type"
        order={TEST_TYPE_ORDER}
        labels={TEST_TYPE_LABELS}
        breakdown={byTestType}
      />
      <BreakdownGroup
        title="Breakdown by Difficulty"
        order={DIFFICULTY_ORDER}
        labels={DIFFICULTY_LABELS}
        breakdown={byDifficulty}
      />
      <BreakdownGroup
        title="Answerable vs Unanswerable"
        order={ANSWERABILITY_ORDER}
        labels={ANSWERABILITY_LABELS}
        breakdown={byAnswerability}
        compact
      />
    </div>
  );
}

function BreakdownGroup({
  title,
  order,
  labels,
  breakdown,
  compact,
}: {
  title: string;
  order: string[];
  labels: Record<string, string>;
  breakdown: Record<string, MetricBreakdown>;
  compact?: boolean;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{title}</h2>
      <div className={`grid gap-3 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
        {order.map((key) => (
          <BreakdownCard key={key} label={labels[key] ?? key} metric={breakdown[key]} />
        ))}
      </div>
    </section>
  );
}

function BreakdownCard({ label, metric }: { label: string; metric: MetricBreakdown | undefined }) {
  if (!metric) return null;

  const percent = metric.pass_rate === null ? 0 : Math.round(metric.pass_rate * 100);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <span className="text-sm font-medium">{label}</span>

      {metric.total === 0 ? (
        <span className="text-sm text-neutral-500 dark:text-neutral-400">0 cases · N/A</span>
      ) : (
        <>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {metric.total} case{metric.total === 1 ? "" : "s"} · {metric.passed} passed /{" "}
            {metric.failed} failed
          </span>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${label} pass rate`}
          >
            <div className="h-full bg-neutral-900 dark:bg-neutral-100" style={{ width: `${percent}%` }} />
          </div>
          <span className="text-sm font-medium">{formatPercent(metric.pass_rate)}</span>
        </>
      )}
    </div>
  );
}
