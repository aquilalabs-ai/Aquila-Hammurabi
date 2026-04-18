import { BookOpen, GraduationCap, Scale } from "lucide-react";
import { useAppStore } from "../../store/app";
import { useCorpusList } from "../../api/hooks/useCorpus";
import { cn } from "../ui/cn";
import type { AppMode } from "../../types/api";

export function TopBar() {
  const { mode, setMode, activeCorpusId } = useAppStore();
  const { data: corpora } = useCorpusList();
  const activeCorpus = corpora?.find((c) => c.id === activeCorpusId);

  return (
    <header className="flex h-12 items-center justify-between border-b border-slate-700 bg-slate-900 px-4 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2">
        <Scale className="h-5 w-5 text-gold-400" />
        <span className="text-sm font-semibold text-gold-400 tracking-wide">
          HAMMURABI
        </span>
        {activeCorpus && (
          <span className="ml-2 flex items-center gap-1 text-xs text-slate-500 hidden sm:flex">
            <span className="text-slate-600">/</span>
            <span className="text-slate-300 font-medium">{activeCorpus.name}</span>
            <span className="text-slate-600 font-mono text-[10px]">{activeCorpus.jurisdiction}</span>
          </span>
        )}
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 p-1">
        <ModeTab
          mode="professional"
          active={mode === "professional"}
          onClick={() => setMode("professional")}
          icon={<BookOpen className="h-3.5 w-3.5" />}
          label="Professional"
        />
        <ModeTab
          mode="student"
          active={mode === "student"}
          onClick={() => setMode("student")}
          icon={<GraduationCap className="h-3.5 w-3.5" />}
          label="Student"
        />
      </div>
    </header>
  );
}

function ModeTab({
  active,
  onClick,
  icon,
  label,
}: {
  mode: AppMode;
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-gold-500/20 text-gold-400 border border-gold-500/30"
          : "text-slate-400 hover:text-slate-200",
      )}
    >
      {icon}
      {label}
    </button>
  );
}
