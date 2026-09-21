"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  ApiError,
  createTextSource,
  deleteSource,
  getSources,
  uploadSource,
  type SourceSummary,
} from "@/lib/api";

type Tab = "paste" | "upload";

export default function SourcesSection({ projectId }: { projectId: number }) {
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab | null>(null);

  function reload() {
    getSources(projectId)
      .then(setSources)
      .catch(() => setLoadError("Unable to load sources."));
  }

  useEffect(reload, [projectId]);

  async function handleDelete(source: SourceSummary) {
    if (!window.confirm(`Delete "${source.filename}"? This cannot be undone.`)) return;
    try {
      await deleteSource(source.id);
      setSources((current) => current?.filter((s) => s.id !== source.id) ?? current);
    } catch {
      window.alert("Unable to delete source. Please try again.");
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">Sources</h2>

      <div className="flex gap-2">
        <TabButton
          active={activeTab === "paste"}
          onClick={() => setActiveTab((t) => (t === "paste" ? null : "paste"))}
        >
          Paste Text
        </TabButton>
        <TabButton
          active={activeTab === "upload"}
          onClick={() => setActiveTab((t) => (t === "upload" ? null : "upload"))}
        >
          Upload File
        </TabButton>
      </div>

      {activeTab === "paste" && (
        <PasteTextForm
          projectId={projectId}
          onCreated={() => {
            setActiveTab(null);
            reload();
          }}
        />
      )}

      {activeTab === "upload" && (
        <UploadFileForm
          projectId={projectId}
          onCreated={() => {
            setActiveTab(null);
            reload();
          }}
        />
      )}

      {loadError && <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>}

      {!loadError && sources === null && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading sources...</p>
      )}

      {!loadError && sources !== null && sources.length === 0 && (
        <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No sources added yet.
        </p>
      )}

      {sources && sources.length > 0 && (
        <ul className="flex flex-col gap-2">
          {sources.map((source) => (
            <SourceRow key={source.id} source={source} onDelete={handleDelete} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium ${
        active
          ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
          : "border border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}

function SourceRow({
  source,
  onDelete,
}: {
  source: SourceSummary;
  onDelete: (source: SourceSummary) => void;
}) {
  return (
    <li className="flex items-start justify-between gap-4 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <div className="flex flex-col gap-1">
        <span className="font-medium">{source.filename}</span>
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          {source.source_type} · {source.character_count.toLocaleString()} characters ·{" "}
          {source.chunk_count} {source.chunk_count === 1 ? "chunk" : "chunks"} · Added{" "}
          {new Date(source.created_at).toLocaleDateString()}
        </span>
        <span className="text-sm text-neutral-500 dark:text-neutral-400">{source.preview}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Link
          href={`/sources/${source.id}`}
          className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          View
        </Link>
        <button
          type="button"
          onClick={() => onDelete(source)}
          className="text-sm font-medium text-red-600 underline-offset-4 hover:underline dark:text-red-400"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

function PasteTextForm({
  projectId,
  onCreated,
}: {
  projectId: number;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!text.trim()) {
      setError("Text is required.");
      return;
    }

    setSubmitting(true);
    try {
      await createTextSource(projectId, { title: title.trim() || undefined, text });
      setTitle("");
      setText("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to add source.");
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
        <label htmlFor="source-title" className="text-sm font-medium">
          Title
        </label>
        <input
          id="source-title"
          type="text"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Employee Handbook"
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="source-text" className="text-sm font-medium">
          Text
        </label>
        <textarea
          id="source-text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={6}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          required
        />
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {submitting ? "Adding..." : "Add Source"}
      </button>
    </form>
  );
}

function UploadFileForm({
  projectId,
  onCreated,
}: {
  projectId: number;
  onCreated: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!file) {
      setError("Choose a file first.");
      return;
    }

    setSubmitting(true);
    try {
      await uploadSource(projectId, file);
      setFile(null);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to upload file.");
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
        <label htmlFor="source-file" className="text-sm font-medium">
          File
        </label>
        <input
          id="source-file"
          type="file"
          accept=".txt,.md,.pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="text-sm"
        />
        {file && (
          <span className="text-xs text-neutral-500 dark:text-neutral-400">{file.name}</span>
        )}
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {submitting ? "Uploading..." : "Upload"}
      </button>
    </form>
  );
}
