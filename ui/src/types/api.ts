// ── Core API types mirroring the FastAPI Pydantic models ──────────────────────

export type RiskSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AppMode = "professional" | "student";
export type ToneLevel = "first_year" | "final_year" | "junior_associate";

// Jobs
export interface JobStatus {
  job_id: string;
  type: string;
  status: "pending" | "running" | "done" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

// Corpus
export interface CorpusSummary {
  id: string;
  name: string;
  jurisdiction: string;
  status: string;
  article_count: number;
  case_count: number;
  chunk_count: number;
  created_at: string;
}

export interface CorpusStats {
  corpus_id: string;
  article_count: number;
  case_count: number;
  chunk_count: number;
}

export interface CorpusIngestResponse {
  corpus_id: string;
  job_id: string;
  status: string;
}

// Documents
export interface DocumentSummary {
  id: string;
  corpus_id: string | null;
  filename: string;
  document_type: string;
  status: string;
  created_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: string;
  jurisdiction: string;
}

export interface RiskFlagItem {
  clause_text: string;
  risk_type: string;
  severity: RiskSeverity;
  explanation: string;
  suggested_improvement: string;
  governing_articles: string[];
}

export interface RiskReport {
  document_id: string;
  jurisdiction: string;
  flags: RiskFlagItem[];
}

export interface AnalysisStatus {
  document_id: string;
  job_id: string | null;
  status: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

// Articles
export interface ArticleNode {
  id: string;
  code: string;
  title: string;
  chapter: string;
  article: string;
  heading: string;
  content: string;
  jurisdiction: string;
  effective_date: string;
  version: string;
  tags: string[];
  keywords: string[];
}

export interface ArticleDetail extends ArticleNode {
  cases: CaseNode[];
  amendments: Amendment[];
}

export interface CaseNode {
  id: string;
  title: string;
  court: string;
  date: string;
  ratio_decidendi: string;
  jurisdiction: string;
}

export interface Amendment {
  id: string;
  date: string;
  content: string;
  is_current: boolean;
}

export interface CitationNetwork {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// Search
export interface SearchResult {
  chunk_id: string;
  source_type: string;
  article_id: string | null;
  case_id: string | null;
  jurisdiction: string;
  content: string;
  score: number;
  tags: string[];
}

// Chat / Sessions
export interface SessionSummary {
  session_id: string;
  corpus_id: string;
  created_at: string;
  updated_at: string;
}

export interface StoredMessage {
  role: "human" | "ai";
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  jurisdiction?: string;
  document_text?: string;
  stream?: boolean;
  mode?: AppMode;
  tone?: ToneLevel;
}

export interface ChatResponse {
  session_id: string;
  response: IracResponse;
}

export interface IracResponse {
  issue: string;
  rule: string;
  application: string;
  conclusion: string;
  citations: Citation[];
  raw?: string;
}

export interface Citation {
  article_id: string;
  code: string;
  article: string;
  heading: string;
  jurisdiction: string;
}

// Draft
export interface DraftRequest {
  prompt: string;
  template_type: string;
  jurisdiction: string;
}

export interface DraftResponse {
  id: string;
  content: string;
  prompt: string;
  jurisdiction: string;
  template_type: string;
  created_at: string;
}

export interface DraftImproveRequest {
  instruction: string;
}

// Graph
export interface GraphNode {
  id: string;
  label: string;
  type: "Article" | "Case" | "Clause" | "Amendment";
  properties: Record<string, unknown>;
  x?: number;
  y?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// Legal tree
export interface LegalTreeNode {
  id: string;
  label: string;
  type: "jurisdiction" | "code" | "title" | "chapter" | "article";
  children?: LegalTreeNode[];
  articleId?: string;
}

// Student mode
export interface ConceptCard {
  article_id: string;
  heading: string;
  plain_explanation: string;
  example: string;
  analogy: string;
  related: string[];
}

export interface QuizQuestion {
  id: string;
  question: string;
  type: "multiple_choice" | "open";
  choices?: string[];
  correct_answer?: string;
  article_id: string;
}

export interface QuizSession {
  id: string;
  questions: QuizQuestion[];
  answers: Record<string, string>;
  score: number | null;
}

export interface CaseSimulation {
  id: string;
  scenario: string;
  relevant_articles: string[];
  model_answer: string;
  difficulty: "easy" | "medium" | "hard";
}

export interface CaseSimulationRequest {
  scenario: string;
  legal_domain?: string;
  jurisdiction?: string;
  session_id?: string;
  stream?: boolean;
}

export interface CaseSimulationResponse {
  session_id: string;
  scenario: string;
  response: string;
}

export interface GenerateCaseRequest {
  topic?: string;
  difficulty?: "easy" | "medium" | "hard";
  jurisdiction?: string;
}

export interface GenerateCaseResponse {
  scenario: string;
  relevant_articles: string[];
  difficulty: string;
}

export interface ProgressData {
  topics_covered: string[];
  quiz_scores: Array<{ session_id: string; score: number; date: string }>;
  flagged_articles: string[];
  weak_areas: string[];
}

// Report Assistant (student mode)
export interface ReportSourceItem {
  type: "web" | "kb";
  title: string;
  article_id?: string;   // kb only
  url?: string;          // web only
  publication?: string;  // web only
  date?: string;         // web only
  excerpt?: string;      // kb only
}

export interface ReportResponse {
  session_id: string;
  response: string;
  sources?: ReportSourceItem[];
}

// SSE event
export interface SSEEvent {
  type: "token" | "status" | "done" | "error";
  content?: string;
  message?: string;
}
