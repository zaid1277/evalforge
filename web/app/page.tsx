"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, createProject, deleteProject, getProjects, type Project } from "@/lib/api";

export default function Home() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    getProjects()
      .then(setProjects)
      .catch(() => setLoadError("Unable to load projects."));
  }, []);

  async function handleDelete(project: Project) {
    if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteProject(project.id);
      setProjects((current) => current?.filter((p) => p.id !== project.id) ?? current);
    } catch {
      window.alert("Unable to delete project. Please try again.");
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-1 flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">EvalForge</h1>
        <p className="text-base text-neutral-600 dark:text-neutral-400">
          Automated LLM Evaluation Dataset Generator
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowForm((current) => !current)}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            {showForm ? "Cancel" : "Create Project"}
          </button>
        </div>

        {showForm && (
          <CreateProjectForm
            onCreated={(project) => {
              setProjects((current) => [project, ...(current ?? [])]);
              setShowForm(false);
            }}
          />
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
          Recent Projects
        </h2>

        {loadError && <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>}

        {!loadError && projects === null && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading projects...</p>
        )}

        {!loadError && projects !== null && projects.length === 0 && (
          <p className="rounded-md border border-dashed border-neutral-300 px-4 py-6 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
            No projects yet.
          </p>
        )}

        {projects && projects.length > 0 && (
          <ul className="flex flex-col gap-3">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} onDelete={handleDelete} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function ProjectCard({
  project,
  onDelete,
}: {
  project: Project;
  onDelete: (project: Project) => void;
}) {
  return (
    <li className="flex items-start justify-between gap-4 rounded-md border border-neutral-200 px-4 py-3 dark:border-neutral-800">
      <div className="flex flex-col gap-1">
        <span className="font-medium">{project.name}</span>
        {project.description && (
          <span className="text-sm text-neutral-600 dark:text-neutral-400">
            {project.description}
          </span>
        )}
        <span className="text-xs text-neutral-400 dark:text-neutral-500">
          Created {new Date(project.created_at).toLocaleDateString()}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Link
          href={`/projects/${project.id}`}
          className="text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          Open
        </Link>
        <button
          type="button"
          onClick={() => onDelete(project)}
          className="text-sm font-medium text-red-600 underline-offset-4 hover:underline dark:text-red-400"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

function CreateProjectForm({ onCreated }: { onCreated: (project: Project) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Project name is required.");
      return;
    }

    setSubmitting(true);
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      onCreated(project);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create project.");
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
        <label htmlFor="project-name" className="text-sm font-medium">
          Project Name
        </label>
        <input
          id="project-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          required
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="project-description" className="text-sm font-medium">
          Description
        </label>
        <textarea
          id="project-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {submitting ? "Creating..." : "Create"}
      </button>
    </form>
  );
}
