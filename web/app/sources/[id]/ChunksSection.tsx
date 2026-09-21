"use client";

import { useEffect, useState } from "react";
import { getSourceChunks, type SourceChunk } from "@/lib/api";

export default function ChunksSection({ sourceId }: { sourceId: number }) {
  const [chunks, setChunks] = useState<SourceChunk[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    getSourceChunks(sourceId)
      .then(setChunks)
      .catch(() => setError("Unable to load chunks."));
  }, [sourceId]);

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
        Chunks{chunks ? ` (${chunks.length})` : ""}
      </h2>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!error && chunks === null && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading chunks...</p>
      )}

      {chunks && (
        <ul className="flex flex-col gap-2">
          {chunks.map((chunk) => {
            const expanded = expandedId === chunk.id;
            return (
              <li
                key={chunk.id}
                className="rounded-md border border-neutral-200 dark:border-neutral-800"
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(expanded ? null : chunk.id)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <span className="font-medium">Chunk {chunk.chunk_index + 1}</span>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400">
                    {chunk.word_count.toLocaleString()} words · {expanded ? "Hide" : "View"} text
                  </span>
                </button>
                {expanded && (
                  <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap border-t border-neutral-200 bg-neutral-50 p-4 text-sm leading-relaxed text-neutral-800 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-200">
                    {chunk.text}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
