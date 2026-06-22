const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export interface Pagination {
  total: number; limit: number; offset: number; has_more: boolean;
}

export interface Paper {
  id: string; source: string; arxiv_id?: string; source_url: string; pdf_url?: string;
  title: string; abstract_preview: string; first_author?: string; author_count: number;
  primary_category?: string; published_date?: string; venue?: string;
  upvotes?: number; decision?: string; keywords: string[];
  one_line_summary?: string; 
  problem_solved?: string;       
  approach_used?: string;        
  key_results?: string;          
  real_world_impact?: string;    
  limitations?: string;          
  relevance_score?: number; ai_tags: string[];
  summarised_at?: string;
}

export interface NewsArticle {
  id: string; source: string; source_display_name: string; url: string;
  title: string; content_preview: string; word_count: number; published_date?: string;
  summary?: string; key_points: string[]; category?: string;
  companies_mentioned: string[]; models_mentioned: string[];
  significance_score?: number; ai_tags: string[]; summarised_at?: string;
}

export interface Tool {
  id: string; source: string; url: string; name: string; description: string;
  stars?: number; votes?: number; likes?: number; downloads?: number; trending_score?: number;
  language?: string; pipeline_task?: string; tags: string[]; author?: string;
  what_it_does?: string; use_cases: string[]; why_trending?: string;
  significance_score?: number; ai_tags: string[]; summarised_at?: string;
}

export interface Benchmark {
  id: string; source: string; model_id: string; model_display_name: string;
  organisation?: string; hf_url?: string; license?: string; context_window?: string;
  params_billions?: number; average_score?: number; ifeval_score?: number;
  bbh_score?: number; math_score?: number; gpqa_score?: number; mmlu_pro_score?: number;
  arena_rank?: number; elo_score?: number; num_votes?: number;
  intelligence_score?: number; speed_tps?: number;
  input_cost_per_1m?: number; output_cost_per_1m?: number;
  model_summary?: string; strengths: string[]; weaknesses: string[];
  best_for?: string; summarised_at?: string;
}

export interface Talk {
  id: string; channel: string; video_url: string; title: string; description: string;
  published_date: string; transcript_available: boolean; duration_seconds?: number; transcript_word_count?: number;
  transcript_preview?: string; summary?: string; key_insights: string[];
  topics_covered: string[]; papers_mentioned: string[]; people_mentioned: string[];
  guest_name?: string; guest_affiliation?: string; difficulty_level?: string;
  relevance_score?: number; ai_tags: string[]; summarised_at?: string;
}

export interface Digest {
  date: string; papers: Paper[]; news: NewsArticle[];
  tools: Tool[]; benchmarks: Benchmark[]; talks: Talk[];
}

export interface SectionStatus {
  total: number; summarised: number; pending: number; last_fetched?: string;
}
export interface Status {
  papers: SectionStatus; news: SectionStatus; tools: SectionStatus;
  benchmarks: SectionStatus; talks: SectionStatus;
}

export const api = {
  digest:     ()                          => apiFetch<Digest>("/digest/today"),
  status:     ()                          => apiFetch<Status>("/status"),
  papers:     (params = "")               => apiFetch<{ data: Paper[];      pagination: Pagination }>(`/papers?${params}`),
  news:       (params = "")               => apiFetch<{ data: NewsArticle[]; pagination: Pagination }>(`/news?${params}`),
  tools:      (params = "")               => apiFetch<{ data: Tool[];       pagination: Pagination }>(`/tools?${params}`),
  benchmarks: (params = "")               => apiFetch<{ data: Benchmark[];  pagination: Pagination }>(`/benchmarks?${params}`),
  talks:      (params = "")               => apiFetch<{ data: Talk[];       pagination: Pagination }>(`/talks?${params}`),
  search:     (q: string, sections = "")  => apiFetch<{ query: string; total: number; results: Record<string, unknown[]> }>(`/search?q=${encodeURIComponent(q)}&sections=${sections}`),
  ask:        askFetch,
};

// ── RAG / Ask ────────────────────────────────────────────────────

export interface AskSource {
  index: number;
  section: "papers" | "news" | "tools" | "benchmarks" | "talks";
  title: string;
  url?: string;
  similarity: number;
}

export interface AskResponse {
  answer: string;
  sources: AskSource[];
  sections_queried: string[];
  query_rewritten: string;
  latency_ms: number;
}

async function askFetch(query: string, opts?: { sections?: string[]; top_k?: number }): Promise<AskResponse> {
  const res = await fetch(`${BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store", // never cache — every question is unique
    body: JSON.stringify({
      query,
      sections: opts?.sections ?? null,
      top_k: opts?.top_k ?? 3,
    }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}: /api/ask`);
  return res.json();
}