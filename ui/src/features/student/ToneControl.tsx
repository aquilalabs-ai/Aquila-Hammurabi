import { GraduationCap, Briefcase, UserCheck } from "lucide-react";
import { useAppStore } from "../../store/app";
import { cn } from "../../components/ui/cn";
import type { ToneLevel } from "../../types/api";

const TONES: {
  value: ToneLevel;
  label: string;
  sublabel: string;
  icon: React.ReactNode;
}[] = [
  {
    value: "first_year",
    label: "First-year student",
    sublabel: "Simple language, many examples, analogies",
    icon: <GraduationCap className="h-4 w-4" />,
  },
  {
    value: "final_year",
    label: "Final-year student",
    sublabel: "Technical vocabulary, nuanced analysis",
    icon: <UserCheck className="h-4 w-4" />,
  },
  {
    value: "junior_associate",
    label: "Junior associate",
    sublabel: "Professional tone, full legal citations",
    icon: <Briefcase className="h-4 w-4" />,
  },
];

export function ToneControl() {
  const { tone, setTone } = useAppStore();

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-slate-400 mb-2">Explanation level</p>
      {TONES.map((t) => (
        <button
          key={t.value}
          onClick={() => setTone(t.value)}
          className={cn(
            "w-full flex items-start gap-3 rounded-xl border p-3 text-left transition-colors",
            tone === t.value
              ? "border-gold-500/40 bg-gold-500/10 text-gold-300"
              : "border-slate-700 bg-slate-800/40 text-slate-400 hover:border-slate-600",
          )}
        >
          <span
            className={cn(
              "mt-0.5 shrink-0",
              tone === t.value ? "text-gold-400" : "text-slate-500",
            )}
          >
            {t.icon}
          </span>
          <div>
            <p className="text-sm font-medium">{t.label}</p>
            <p className="text-xs opacity-70">{t.sublabel}</p>
          </div>
          {tone === t.value && (
            <span className="ml-auto shrink-0 h-2 w-2 rounded-full bg-gold-400 self-center" />
          )}
        </button>
      ))}
    </div>
  );
}
