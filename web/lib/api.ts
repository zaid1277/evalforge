// Central place for talking to the EvalForge backend API.
// Keeping the base URL and fetch logic here (instead of scattered across
// components) means the API address only needs to change in one place.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  // For FormData bodies (file uploads) the browser must set its own
  // multipart/form-data header (with boundary) -- setting Content-Type
  // ourselves would break that, so only default it for JSON bodies.
  const isFormData = options?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      ...options,
      headers: isFormData
        ? options?.headers
        : { "Content-Type": "application/json", ...options?.headers },
    });
  } catch {
    // The backend is down or unreachable (e.g. not started, wrong URL).
    throw new ApiError("Unable to reach the EvalForge API.", 0);
  }

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      return data.detail;
    }
  } catch {
    // Response body wasn't JSON; fall through to the generic message below.
  }
  return `Request failed with status ${response.status}.`;
}

export type HealthResponse = {
  status: string;
};

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export type Project = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
};

export type CreateProjectInput = {
  name: string;
  description?: string;
};

export function getProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function getProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`);
}

export function createProject(input: CreateProjectInput): Promise<Project> {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/projects/${id}`, { method: "DELETE" });
}

export type SourceType = "text" | "txt" | "markdown" | "pdf";

// Lighter shape used by the source list -- see SourceDocumentSummary on
// the backend. Full text is only fetched when a single source is opened.
export type SourceSummary = {
  id: number;
  filename: string;
  source_type: SourceType;
  created_at: string;
  character_count: number;
  preview: string;
  chunk_count: number;
};

export type SourceDocument = {
  id: number;
  project_id: number;
  filename: string;
  source_type: SourceType;
  raw_text: string;
  created_at: string;
  chunk_count: number;
};

export type SourceChunk = {
  id: number;
  source_document_id: number;
  source_filename: string;
  chunk_index: number;
  text: string;
  word_count: number;
};

export type CreateTextSourceInput = {
  title?: string;
  text: string;
};

export function getSources(projectId: number): Promise<SourceSummary[]> {
  return apiFetch<SourceSummary[]>(`/projects/${projectId}/sources`);
}

export function getSource(sourceId: number): Promise<SourceDocument> {
  return apiFetch<SourceDocument>(`/sources/${sourceId}`);
}

export function createTextSource(
  projectId: number,
  input: CreateTextSourceInput
): Promise<SourceDocument> {
  return apiFetch<SourceDocument>(`/projects/${projectId}/sources/text`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function uploadSource(projectId: number, file: File): Promise<SourceDocument> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<SourceDocument>(`/projects/${projectId}/sources/upload`, {
    method: "POST",
    body: formData,
  });
}

export function deleteSource(sourceId: number): Promise<void> {
  return apiFetch<void>(`/sources/${sourceId}`, { method: "DELETE" });
}

export function getSourceChunks(sourceId: number): Promise<SourceChunk[]> {
  return apiFetch<SourceChunk[]>(`/sources/${sourceId}/chunks`);
}

export type CaseDifficulty = "easy" | "medium";
export type GenerationDifficulty = CaseDifficulty | "mixed";
export type TestType = "direct" | "multi_step" | "unanswerable";
export type EvaluationStatus = "generated" | "approved" | "rejected";

export type EvaluationCase = {
  id: number;
  project_id: number;
  question: string;
  reference_answer: string | null;
  category: string;
  difficulty: CaseDifficulty;
  test_type: TestType;
  is_answerable: boolean;
  status: EvaluationStatus;
  source_chunk_ids: number[];
  // Highest cosine similarity to another case's question in this project
  // (null until there's another case to compare against). A heuristic,
  // not proof of an exact duplicate -- see api/app/services/duplicate_service.py.
  duplicate_score: number | null;
  // Server-computed: duplicate_score >= the configured threshold.
  is_possible_duplicate: boolean;
  // Cosine similarity between reference_answer and its exact linked
  // source evidence (null for unanswerable cases -- there is no
  // reference_answer to compare). A heuristic, not a factual-correctness
  // check -- see api/app/services/grounding_service.py.
  grounding_score: number | null;
  // Server-computed: grounding_score is not null AND below the
  // configured threshold.
  needs_grounding_review: boolean;
  created_at: string;
};

export type GenerationRequestInput = {
  count: number;
  difficulty: GenerationDifficulty;
  test_types: TestType[];
};

export type GenerationResponse = {
  generated_count: number;
  provider: string;
  model: string;
  cases: EvaluationCase[];
};

export function generateEvaluationCases(
  projectId: number,
  input: GenerationRequestInput
): Promise<GenerationResponse> {
  return apiFetch<GenerationResponse>(`/projects/${projectId}/generate`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getEvaluationCases(projectId: number): Promise<EvaluationCase[]> {
  return apiFetch<EvaluationCase[]>(`/projects/${projectId}/cases`);
}

export function getEvaluationCase(caseId: number): Promise<EvaluationCase> {
  return apiFetch<EvaluationCase>(`/cases/${caseId}`);
}

// Every field optional -- only send what's actually changing. `id`,
// `project_id`, `created_at`, and `source_chunk_ids` can't be edited.
export type EvaluationCaseUpdate = {
  question?: string;
  reference_answer?: string | null;
  category?: string;
  difficulty?: CaseDifficulty;
  test_type?: TestType;
  is_answerable?: boolean;
  status?: EvaluationStatus;
};

export function updateEvaluationCase(
  caseId: number,
  patch: EvaluationCaseUpdate
): Promise<EvaluationCase> {
  return apiFetch<EvaluationCase>(`/cases/${caseId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getEvaluationCaseSources(caseId: number): Promise<SourceChunk[]> {
  return apiFetch<SourceChunk[]>(`/cases/${caseId}/sources`);
}

export type ExportFormat = "jsonl" | "csv";
export type ExportStatusFilter = "approved" | "generated" | "rejected" | "all";

export type ExportResult = {
  blob: Blob;
  filename: string;
};

// A file download, not JSON, so this bypasses apiFetch (which always calls
// response.json()) and talks to fetch directly.
export async function exportDataset(
  projectId: number,
  format: ExportFormat,
  status: ExportStatusFilter
): Promise<ExportResult> {
  const params = new URLSearchParams({ format, status });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/projects/${projectId}/export?${params}`, {
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Unable to reach the EvalForge API.", 0);
  }

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }

  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `evalforge-dataset.${format}`;

  return { blob: await response.blob(), filename };
}

export type PublicConfig = {
  provider: string;
  model: string;
  mock_mode: boolean;
};

export function getPublicConfig(): Promise<PublicConfig> {
  return apiFetch<PublicConfig>("/config/public");
}

export type EvaluationResult = {
  id: number;
  evaluation_case_id: number;
  question: string;
  reference_answer: string | null;
  model_response: string;
  // Cosine similarity between model_response and reference_answer (null
  // for unanswerable cases, which are judged instead -- see
  // api/app/services/evaluation_service.py). A heuristic, not a
  // correctness guarantee: see EvaluationSection's limitation note.
  semantic_similarity: number | null;
  passed: boolean;
  evaluation_reason: string;
  test_type: TestType;
  difficulty: CaseDifficulty;
  created_at: string;
};

export type EvaluationRunSummary = {
  id: number;
  project_id: number;
  provider: string;
  model_name: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  created_at: string;
};

export type EvaluationRun = EvaluationRunSummary & {
  results: EvaluationResult[];
};

export function runEvaluation(projectId: number): Promise<EvaluationRun> {
  return apiFetch<EvaluationRun>(`/projects/${projectId}/evaluations`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getEvaluations(projectId: number): Promise<EvaluationRunSummary[]> {
  return apiFetch<EvaluationRunSummary[]>(`/projects/${projectId}/evaluations`);
}

export function getEvaluation(evaluationId: number): Promise<EvaluationRun> {
  return apiFetch<EvaluationRun>(`/evaluations/${evaluationId}`);
}

// M10: read-only aggregation over an evaluation run's already-persisted
// results (see api/app/services/results_service.py) -- no rescoring, no
// Gemini/MiniLM calls.
export type MetricBreakdown = {
  total: number;
  passed: number;
  failed: number;
  // null (not 0) when total is 0 -- an empty category has no pass rate.
  pass_rate: number | null;
};

export type EvaluationDashboard = {
  evaluation_id: number;
  project_id: number;
  provider: string;
  model_name: string;
  created_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number | null;
  // Keyed by TestType.value ("direct" | "multi_step" | "unanswerable").
  by_test_type: Record<string, MetricBreakdown>;
  // Keyed by CaseDifficulty ("easy" | "medium").
  by_difficulty: Record<string, MetricBreakdown>;
  // Keyed by "answerable" | "unanswerable".
  by_answerability: Record<string, MetricBreakdown>;
};

export function getEvaluationDashboard(evaluationId: number): Promise<EvaluationDashboard> {
  return apiFetch<EvaluationDashboard>(`/evaluations/${evaluationId}/dashboard`);
}
