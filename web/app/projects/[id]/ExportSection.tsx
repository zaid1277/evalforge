"use client";

import { useState } from "react";
import {
  ApiError,
  exportDataset,
  type EvaluationCase,
  type ExportFormat,
  type ExportStatusFilter,
} from "@/lib/api";

const FORMAT_OPTIONS: { value: ExportFormat; label: string }[] = [
  { value: "jsonl", label: "JSONL" },
  { value: "csv", label: "CSV" },
];

const STATUS_OPTIONS: { value: ExportStatusFilter; label: string }[] = [
  { value: "approved", label: "Approved" },
  { value: "generated", label: "Generated" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export default function ExportSection({
  projectId,
  cases,
}: {
  projectId: number;
  cases: EvaluationCase[] | null;
}) {
  const [format, setFormat] = useState<ExportFormat>("jsonl");
  const [status, setStatus] = useState<ExportStatusFilter>("approved");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reuses the case list the page already loaded for the Evaluation Cases
  // section -- no extra API call just to show counts here.
  const matchingCount =
    cases === null ? null : status === "all" ? cases.length : cases.filter((c) => c.status === status).length;

  async function handleDownload() {
    setError(null);
    setDownloading(true);
    try {
      const { blob, filename } = await exportDataset(projectId, format, status);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to export dataset.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Export Dataset</h2>

      <div className="flex flex-wrap items-end gap-6">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium">Format</span>
          <div className="flex gap-2">
            {FORMAT_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setFormat(value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  format === value
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium">Cases</span>
          <div className="flex gap-2">
            {STATUS_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatus(value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  status === value
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {matchingCount === null
          ? "Loading case counts..."
          : `${matchingCount} case${matchingCount === 1 ? "" : "s"} match this selection.`}
      </p>

      {status === "generated" && (
        <p className="text-xs text-orange-700 dark:text-orange-400">
          Generated / not reviewed -- these cases have not been approved yet.
        </p>
      )}

      <button
        type="button"
        onClick={handleDownload}
        disabled={downloading || matchingCount === 0}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {downloading ? "Preparing download..." : "Download"}
      </button>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </section>
  );
}
