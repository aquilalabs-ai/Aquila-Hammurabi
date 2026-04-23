import {
  BookOpen,
  HelpCircle,
  Scale,
  TrendingUp,
  ShieldAlert,
  Settings2,
  GraduationCap,
  Database,
} from "lucide-react";
import { ConceptCards } from "./ConceptCards";
import { IRACWalkthrough } from "./IRACWalkthrough";
import { QuizPanel } from "./QuizPanel";
import { CaseSimulation } from "./CaseSimulation";
import { ProgressTracker } from "./ProgressTracker";
import { SimplifiedRiskReport } from "./SimplifiedRiskReport";
import { ToneControl } from "./ToneControl";
import { ReportAssistant } from "./ReportAssistant";
import { useAppStore } from "../../store/app";
import type { StudentTab } from "../../store/app";
import { cn } from "../../components/ui/cn";

const TABS: { key: StudentTab; label: string; icon: React.ReactNode }[] = [
  { key: "concepts", label: "Concepts", icon: <BookOpen className="h-3.5 w-3.5" /> },
  { key: "irac", label: "IRAC Walk-through", icon: <Scale className="h-3.5 w-3.5" /> },
  { key: "quiz", label: "Quiz", icon: <HelpCircle className="h-3.5 w-3.5" /> },
  { key: "simulation", label: "Case Simulation", icon: <Scale className="h-3.5 w-3.5" /> },
  { key: "report", label: "Report Assistant", icon: <GraduationCap className="h-3.5 w-3.5" /> },
  { key: "progress", label: "Progress", icon: <TrendingUp className="h-3.5 w-3.5" /> },
  { key: "risk", label: "Risk (plain)", icon: <ShieldAlert className="h-3.5 w-3.5" /> },
  { key: "settings", label: "Tone", icon: <Settings2 className="h-3.5 w-3.5" /> },
];

const CORPUS_DEPENDENT_TABS: StudentTab[] = ["concepts", "irac", "quiz", "simulation", "risk"];

export function StudentMode() {
  const { activeCorpusId, activeStudentTab: tab, setActiveStudentTab: setTab } = useAppStore();
  const needsCorpus = CORPUS_DEPENDENT_TABS.includes(tab);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Horizontal tab bar */}
      <div className="flex items-center gap-0.5 border-b border-slate-700 bg-slate-900 px-3 py-1.5 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap",
              tab === t.key
                ? "bg-slate-700 text-slate-100"
                : "text-slate-500 hover:text-slate-300",
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* No corpus warning */}
      {needsCorpus && !activeCorpusId && (
        <div className="flex items-center gap-2.5 border-b border-amber-700/40 bg-amber-900/20 px-4 py-2.5 text-xs text-amber-300">
          <Database className="h-3.5 w-3.5 shrink-0" />
          Select a corpus from the left sidebar to use this module.
        </div>
      )}

      {/* Tab content — all panels stay mounted so local state is preserved across tab switches */}
      <div className="relative flex-1 overflow-y-auto">
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "concepts" && "hidden")}><ConceptCards /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "irac" && "hidden")}><IRACWalkthrough /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "quiz" && "hidden")}><QuizPanel /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "simulation" && "hidden")}><CaseSimulation /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "report" && "hidden")}><ReportAssistant /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "progress" && "hidden")}><ProgressTracker /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "risk" && "hidden")}><SimplifiedRiskReport /></div>
        <div className={cn("p-4 max-w-2xl mx-auto w-full", tab !== "settings" && "hidden")}><ToneControl /></div>
      </div>
    </div>
  );
}
