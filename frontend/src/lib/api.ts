/**
 * Core Engine API client
 * Uses Tauri HTTP plugin fetch (falls back to browser fetch outside Tauri).
 */
import { fetch as pluginFetch } from "@tauri-apps/plugin-http";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function tauriFetch(url: string, init?: RequestInit): Promise<Response> {
  return pluginFetch(url, init) as unknown as Promise<Response>;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await tauriFetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BookEntry {
  book_id: string;
  display_name: string;
  book_root: string;
}

export interface RegistryResponse {
  books: BookEntry[];
}

interface _RegistryRaw {
  books: Record<string, BookEntry>;
}

export interface StageStatus {
  status: string;
  updated_at: string;
  note: string;
}

export interface ChapterInfo {
  title: string;
  part?: string;
  stages: Record<string, StageStatus>;
}

export interface PipelineResponse {
  book_id: string;
  chapter_sequence: string[];
  chapters: Record<string, ChapterInfo>;
}

export interface GateFailure {
  chapter_id: string;
  stage_id: string;
  reason?: string;
}

export interface HealingStatus {
  book_id: string;
  total_chapters: number;
  completion_rate: number;
  completed: number;
  pending: number;
  gate_failed_count: number;
  gate_failed: GateFailure[];
}

/** @deprecated use HealingStatus */
export type HealthStatus = HealingStatus;

export interface BookDetail {
  display_name: string;
  book_id: string;
  book_root?: string;
}

export interface BookDetailResponse {
  registry_entry: BookEntry;
  book: BookDetail;
  book_level_stages: Record<string, StageStatus>;
  chapter_count: number;
}

export interface QACheck {
  check: string;
  passed: boolean;
  detail: string;
}

export interface QAReport {
  overall_pass: boolean;
  checks_passed: number;
  checks_total: number;
  checks: QACheck[];
  failed_checks: string[];
}

export interface WorkOrderItem {
  rank: number;
  chapter_id: string;
  stage_id: string;
  agent_id: string;
  action: string;
}

export interface WorkOrderResponse {
  order_id: string;
  book_id: string;
  priority_queue: WorkOrderItem[];
  gate_failures: GateFailure[];
}

export interface StageRunResponse {
  status: string;
  message?: string;
}

export interface LicenseStatus {
  valid: boolean;
  plan: string;
  key_masked: string;
}

export interface AppSettings {
  gemini_api_key: string;
  openai_api_key: string;
  default_model: string;
  app_version: string;
}

export interface BootstrapBookRequest {
  book_id: string;
  display_name: string;
  book_root: string;
  source_file: string;
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export const registry = {
  listBooks: async (): Promise<RegistryResponse> => {
    const raw = await apiFetch<_RegistryRaw>("/engine/registry/books");
    const booksObj = raw.books ?? {};
    return {
      books: Object.values(booksObj),
    };
  },

  getBook: (bookId: string) =>
    apiFetch<BookDetailResponse>(`/engine/registry/books/${bookId}`),

  bootstrapBook: (req: BootstrapBookRequest) =>
    apiFetch<{ ok: boolean; book_id: string }>("/engine/registry/books", {
      method: "POST",
      body: JSON.stringify(req),
    }),
};

// ---------------------------------------------------------------------------
// Stage / Pipeline
// ---------------------------------------------------------------------------

export const stage = {
  getPipeline: (bookId: string) =>
    apiFetch<PipelineResponse>(`/engine/stage/pipeline/${bookId}`),

  run: (bookId: string, stageId: string, chapterId?: string) =>
    apiFetch<StageRunResponse>("/engine/stage/run", {
      method: "POST",
      body: JSON.stringify({ book_id: bookId, stage_id: stageId, chapter_id: chapterId }),
    }),

  transition: (bookId: string, stageId: string, toStatus: string, chapterId?: string) =>
    apiFetch("/engine/stage/transition", {
      method: "POST",
      body: JSON.stringify({ book_id: bookId, stage_id: stageId, to_status: toStatus, chapter_id: chapterId }),
    }),
};

// ---------------------------------------------------------------------------
// Healing
// ---------------------------------------------------------------------------

export const healing = {
  status: (bookId: string) =>
    apiFetch<HealingStatus>(`/engine/healing/status?book_id=${bookId}`),
};

// ---------------------------------------------------------------------------
// QA
// ---------------------------------------------------------------------------

export const qa = {
  run: (bookId: string) =>
    apiFetch<{ ok: boolean }>(`/engine/qa/run?book_id=${bookId}`, { method: "POST" }),

  report: (bookId: string) =>
    apiFetch<QAReport>(`/engine/qa/report?book_id=${bookId}`),

  getReport: (bookId: string) =>
    apiFetch<QAReport>(`/engine/qa/report?book_id=${bookId}`),
};

// ---------------------------------------------------------------------------
// Work Order
// ---------------------------------------------------------------------------

export const workOrder = {
  issue: (bookId: string) =>
    apiFetch<WorkOrderResponse>(`/engine/work-order/issue`, {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    }),

  telemetry: (bookId: string) =>
    apiFetch<Record<string, unknown>>(`/engine/work-order/telemetry?book_id=${bookId}`),
};

// ---------------------------------------------------------------------------
// Publish / Google Books
// ---------------------------------------------------------------------------

export interface StyleGuide {
  id: string;
  name: string;
  description: string;
  target: string;
  css_class: string;
  params?: Record<string, string | number | boolean>;
  book_id?: string;
  saved_at?: string;
}

export interface EpubMetadata {
  book_id?: string;
  title: string;
  subtitle: string;
  author: string;
  publisher: string;
  publication_date: string;
  language: string;
  isbn13: string;
  google_books_id: string;
  description: string;
  keywords: string[];
  bisac_code: string;
  thema_code: string;
  age_rating: string;
  adult_content: boolean;
  identifier?: string;
  updated_at?: string;
}

export interface MetadataPreview {
  metadata: EpubMetadata;
  opf_xml: string;
  bisac_categories: { code: string; label: string; bisac: string }[];
  thema_categories: { code: string; label: string }[];
  languages: { code: string; label: string }[];
  age_ratings: string[];
  errors: string[];
  valid: boolean;
}

export interface KeywordData {
  keywords: string[];
  longtail_keywords: string[];
  bisac_code?: string;
  thema_code?: string;
  description?: string;
  reasoning?: string;
  source?: string;
  generated_at?: string;
}

export interface EpubExportResult {
  stage?: string;
  book_id?: string;
  epub_path?: string;
  epub_name?: string;
  file_size_mb?: number;
  chapter_count?: number;
  toc_entries?: number;
  compliance?: Record<string, unknown>;
  completed_at?: string;
  status?: string;
}

export const publish = {
  listStyleGuides: () =>
    apiFetch<{ style_guides: StyleGuide[] }>("/engine/publish/style-guides"),

  getStyleGuide: (bookId: string) =>
    apiFetch<StyleGuide>(`/engine/publish/style-guide/${bookId}`),

  saveStyleGuide: (bookId: string, templateId: string, paramsOverride?: Record<string, unknown>) =>
    apiFetch<{ ok: boolean; guide: StyleGuide }>(`/engine/publish/style-guide/${bookId}`, {
      method: "POST",
      body: JSON.stringify({ template_id: templateId, params_override: paramsOverride }),
    }),

  getMetadata: (bookId: string) =>
    apiFetch<MetadataPreview>(`/engine/publish/metadata/${bookId}`),

  saveMetadata: (bookId: string, data: Partial<EpubMetadata>) =>
    apiFetch<{ ok: boolean; errors: string[]; metadata: EpubMetadata }>(
      `/engine/publish/metadata/${bookId}`,
      { method: "PUT", body: JSON.stringify(data) }
    ),

  generateKeywords: (bookId: string) =>
    apiFetch<KeywordData>(`/engine/publish/keywords/generate/${bookId}`, { method: "POST" }),

  getKeywords: (bookId: string) =>
    apiFetch<KeywordData>(`/engine/publish/keywords/${bookId}`),

  saveKeywords: (bookId: string, keywords: string[], longtailKeywords: string[] = []) =>
    apiFetch<{ ok: boolean; keywords: KeywordData }>(`/engine/publish/keywords/${bookId}`, {
      method: "PUT",
      body: JSON.stringify({ keywords, longtail_keywords: longtailKeywords }),
    }),

  exportEpub: (bookId: string) =>
    apiFetch<EpubExportResult>(`/engine/publish/export/${bookId}`, { method: "POST" }),

  exportStatus: (bookId: string) =>
    apiFetch<EpubExportResult>(`/engine/publish/export/${bookId}/status`),
};

// ---------------------------------------------------------------------------
// License
// ---------------------------------------------------------------------------

export const license = {
  validate: (key: string) =>
    apiFetch<LicenseStatus>("/engine/license/validate", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),

  status: () => apiFetch<LicenseStatus>("/engine/license/status"),
};

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export const settings = {
  get: () => apiFetch<AppSettings>("/engine/settings"),

  update: (data: Partial<AppSettings>) =>
    apiFetch<AppSettings>("/engine/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};
