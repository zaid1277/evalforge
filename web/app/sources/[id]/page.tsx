"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, deleteSource, getSource, type SourceDocument } from "@/lib/api";
import ChunksSection from "./ChunksSection";

export default function SourceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sourceId = Number(params.id);
  const invalidId = Number.isNaN(sourceId);

  const [source, setSource] = useState<SourceDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!invalidId);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    getSource(sourceId)
      .then((data) => {
        if (!cancelled) setSource(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? "Source not found."
            : "Unable to load source."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sourceId, invalidId]);

  const displayError = invalidId ? "Source not found." : error;

  async function handleDelete() {
    if (!source) return;
    if (!window.confirm(`Delete "${source.filename}"? This cannot be undone.`)) return;

    setDeleting(true);
    try {
      await deleteSource(source.id);
      router.push(`/projects/${source.project_id}`);
    } catch {
      window.alert("Unable to delete source. Please try again.");
      setDeleting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-1 flex-col gap-6 px-6 py-16">
      <Link
        href={source ? `/projects/${source.project_id}` : "/"}
        className="text-sm text-neutral-500 hover:underline dark:text-neutral-400"
      >
        ← Back to project
      </Link>

      {loading && <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading source...</p>}

      {!loading && displayError && (
        <p className="text-sm text-red-600 dark:text-red-400">{displayError}</p>
      )}

      {!loading && !displayError && source && (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{source.filename}</h1>
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              {source.source_type} · {source.raw_text.length.toLocaleString()} characters ·{" "}
              {source.chunk_count} {source.chunk_count === 1 ? "chunk" : "chunks"} · Added{" "}
              {new Date(source.created_at).toLocaleDateString()}
            </p>
          </header>

          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="self-start rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 disabled:opacity-50 dark:border-red-800 dark:text-red-400"
          >
            {deleting ? "Deleting..." : "Delete Source"}
          </button>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
              Full Text
            </h2>
            <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-4 text-sm leading-relaxed text-neutral-800 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-200">
              {source.raw_text}
            </pre>
          </section>

          <ChunksSection sourceId={source.id} />
        </>
      )}
    </main>
  );
}
