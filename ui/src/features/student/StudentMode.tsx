import { useState } from "react";
import {
  BookOpen,
  HelpCircle,
  Scale,
  TrendingUp,
  ShieldAlert,
  Settings2,
  GraduationCap,
} from "lucide-react";
import { ConceptCards } from "./ConceptCards";
import { IRACWalkthrough } from "./IRACWalkthrough";
import { QuizPanel } from "./QuizPanel";
import { CaseSimulation } from "./CaseSimulation";
import { ProgressTracker } from "./ProgressTracker";
import { SimplifiedRiskReport } from "./SimplifiedRiskReport";
import { ToneControl } from "./ToneControl";
import { ReportAssistant } from "./ReportAssistant";
import { cn } from "../../components/ui/cn";

type StudentTab = "concepts" | "irac" | "quiz" | "simulation" | "report" | "progress" | "risk" | "settings";

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

export function StudentMode() {
  const [tab, setTab] = useState<StudentTab>("concepts");

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

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4 max-w-2xl mx-auto w-full">
        {tab === "concepts" && <ConceptCards />}
        {tab === "irac" && <IRACWalkthrough />}
        {tab === "quiz" && <QuizPanel />}
        {tab === "simulation" && <CaseSimulation />}
        {tab === "report" && <ReportAssistant />}
        {tab === "progress" && <ProgressTracker />}
        {tab === "risk" && <SimplifiedRiskReport />}
        {tab === "settings" && <ToneControl />}
      </div>
    </div>
  );
}
