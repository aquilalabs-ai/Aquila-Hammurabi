import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AppMode, QuizQuestion, ToneLevel } from "../types/api";

export type ProfessionalTab = "chat" | "upload" | "risk";
export type StudentTab = "concepts" | "irac" | "quiz" | "simulation" | "report" | "progress" | "risk" | "settings";

interface AppState {
  // Mode
  mode: AppMode;
  setMode: (mode: AppMode) => void;

  // Corpus
  activeCorpusId: string | null;
  setActiveCorpus: (id: string | null) => void;

  // Document
  activeDocumentId: string | null;
  setActiveDocument: (id: string | null) => void;

  // Session
  activeSessionId: string | null;
  setActiveSession: (id: string | null) => void;

  // Professional mode tab (persisted so mode-switching preserves position)
  activeProfessionalTab: ProfessionalTab;
  setActiveProfessionalTab: (tab: ProfessionalTab) => void;

  // Student mode tab (persisted so mode-switching preserves position)
  activeStudentTab: StudentTab;
  setActiveStudentTab: (tab: StudentTab) => void;

  // Research sidebar
  researchSidebarOpen: boolean;
  toggleResearchSidebar: () => void;

  // Document viewer
  documentViewerOpen: boolean;
  toggleDocumentViewer: () => void;

  // Citation graph
  citationGraphOpen: boolean;
  setCitationGraphOpen: (open: boolean) => void;

  // Drafting panel
  draftingPanelOpen: boolean;
  toggleDraftingPanel: () => void;

  // Student tone
  tone: ToneLevel;
  setTone: (tone: ToneLevel) => void;

  // Progress tracking (student mode)
  topicsCovered: string[];
  markTopicCovered: (articleId: string) => void;
  flaggedArticles: string[];
  toggleFlaggedArticle: (articleId: string) => void;
  quizScores: Array<{
    session_id: string;
    score: number;
    date: string;
    topic?: string;
    questions?: QuizQuestion[];
  }>;
  addQuizScore: (session_id: string, score: number, questions?: QuizQuestion[], topic?: string) => void;
  pendingRetakeQuiz: { questions: QuizQuestion[]; topic?: string } | null;
  setPendingRetakeQuiz: (quiz: { questions: QuizQuestion[]; topic?: string } | null) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      mode: "professional",
      setMode: (mode) => set({ mode }),

      activeCorpusId: null,
      setActiveCorpus: (id) =>
        set({ activeCorpusId: id, activeSessionId: null, activeDocumentId: null, activeProfessionalTab: "chat" }),

      activeDocumentId: null,
      setActiveDocument: (id) => set({ activeDocumentId: id }),

      activeSessionId: null,
      setActiveSession: (id) => set({ activeSessionId: id }),

      activeProfessionalTab: "chat",
      setActiveProfessionalTab: (tab) => set({ activeProfessionalTab: tab }),

      activeStudentTab: "concepts",
      setActiveStudentTab: (tab) => set({ activeStudentTab: tab }),

      researchSidebarOpen: false,
      toggleResearchSidebar: () =>
        set((s) => ({ researchSidebarOpen: !s.researchSidebarOpen })),

      documentViewerOpen: false,
      toggleDocumentViewer: () =>
        set((s) => ({ documentViewerOpen: !s.documentViewerOpen })),

      citationGraphOpen: false,
      setCitationGraphOpen: (open) => set({ citationGraphOpen: open }),

      draftingPanelOpen: false,
      toggleDraftingPanel: () =>
        set((s) => ({ draftingPanelOpen: !s.draftingPanelOpen })),

      tone: "final_year",
      setTone: (tone) => set({ tone }),

      topicsCovered: [],
      markTopicCovered: (articleId) =>
        set((s) => ({
          topicsCovered: s.topicsCovered.includes(articleId)
            ? s.topicsCovered
            : [...s.topicsCovered, articleId],
        })),

      flaggedArticles: [],
      toggleFlaggedArticle: (articleId) =>
        set((s) => ({
          flaggedArticles: s.flaggedArticles.includes(articleId)
            ? s.flaggedArticles.filter((a) => a !== articleId)
            : [...s.flaggedArticles, articleId],
        })),

      quizScores: [],
      addQuizScore: (session_id, score, questions?, topic?) =>
        set((s) => ({
          quizScores: [
            ...s.quizScores,
            { session_id, score, date: new Date().toISOString(), questions, topic },
          ],
        })),

      pendingRetakeQuiz: null,
      setPendingRetakeQuiz: (quiz) => set({ pendingRetakeQuiz: quiz }),
    }),
    { name: "hammurabi-app" },
  ),
);
