"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  deleteProject,
  getEvaluationCases,
  getProject,
  type EvaluationCase,
  type Project,
} from "@/lib/api";
import EvaluationSection from "./EvaluationSection";
import ExportSection from "./ExportSection";
import GenerationSection from "./GenerationSection";
import SourcesSection from "./SourcesSection";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Number(params.id);
  const invalidId = Number.isNaN(projectId);

  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!invalidId);
  const [deleting, setDeleting] = useState(false);

  const [cases, setCases] = useState<EvaluationCase[] | null>(null);
  const [casesLoadError, setCasesLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    getProject(projectId)
      .then((data) => {
        if (!cancelled) setProject(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError && err.status === 404 ? "Project not found." : "Unable to load project.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, invalidId]);

  const reloadCases = useCallback(() => {
    getEvaluationCases(projectId)
      .then(setCases)
      .catch(() => setCasesLoadError("Unable to load evaluation cases."));
  }, [projectId]);

  useEffect(() => {
    if (invalidId) return;
    reloadCases();
  }, [invalidId, reloadCases]);

  function handleCaseUpdated(updated: EvaluationCase) {
    setCases((current) => current?.map((c) => (c.id === updated.id ? updated : c)) ?? current);
  }

  const displayError = invalidId ? "Project not found." : error;

  async function handleDelete() {
    if (!project) return;
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) return;

    setDeleting(true);
    try {
      await deleteProject(project.id);
      router.push("/");
    } catch {
      window.alert("Unable to delete project. Please try again.");
      setDeleting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <Link href="/" className="text-sm text-neutral-500 hover:underline dark:text-neutral-400">
        ← Back to projects
      </Link>

      {loading && <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading project...</p>}

      {!loading && displayError && (
        <p className="text-sm text-red-600 dark:text-red-400">{displayError}</p>
      )}

      {!loading && !displayError && project && (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
            {project.description && (
              <p className="text-base text-neutral-600 dark:text-neutral-400">
                {project.description}
              </p>
            )}
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              Created {new Date(project.created_at).toLocaleDateString()}
            </p>
          </header>

          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="self-start rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 disabled:opacity-50 dark:border-red-800 dark:text-red-400"
          >
            {deleting ? "Deleting..." : "Delete Project"}
          </button>

          <SourcesSection projectId={project.id} />

          <GenerationSection
            projectId={project.id}
            cases={cases}
            loadError={casesLoadError}
            reload={reloadCases}
            onCaseUpdated={handleCaseUpdated}
          />

          <ExportSection projectId={project.id} cases={cases} />

          <EvaluationSection projectId={project.id} cases={cases} />
        </>
      )}
    </main>
  );
}
