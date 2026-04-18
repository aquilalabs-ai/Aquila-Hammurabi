import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, FileText, Gavel, CheckCircle2, ChevronRight } from "lucide-react";
import { cn } from "../../components/ui/cn";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import type { IracResponse } from "../../types/api";

type StepKey = "issue" | "rule" | "application" | "conclusion";

export const IRAC_STEPS: {
  key: StepKey;
  label: string;
  icon: React.ReactNode;
  color: string;
  description: string;
}[] = [
  {
    key: "issue",
    label: "Issue",
    icon: <BookOpen className="h-4 w-4" />,
    color: "text-blue-400 border-blue-400/30 bg-blue-400/5",
    description: "Identifying the legal question",
  },
  {
    key: "rule",
    label: "Rule",
    icon: <FileText className="h-4 w-4" />,
    color: "text-purple-400 border-purple-400/30 bg-purple-400/5",
    description: "The applicable law or principle",
  },
  {
    key: "application",
    label: "Application",
    icon: <Gavel className="h-4 w-4" />,
    color: "text-amber-400 border-amber-400/30 bg-amber-400/5",
    description: "Applying the rule to the facts",
  },
  {
    key: "conclusion",
    label: "Conclusion",
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: "text-green-400 border-green-400/30 bg-green-400/5",
    description: "The legal outcome",
  },
];

const MD_COMPONENTS: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => <h1 className="text-base font-bold text-slate-200 mb-2 mt-3">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-bold text-slate-200 mb-1.5 mt-2.5">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-slate-300 mb-1 mt-2">{children}</h3>,
  p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="text-slate-300">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-200">{children}</strong>,
  em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
  code: ({ children }) => (
    <code className="bg-slate-800 text-amber-300 rounded px-1 py-0.5 text-xs font-mono">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="bg-slate-800 rounded-lg p-3 mb-2 overflow-x-auto text-xs font-mono">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-slate-600 pl-3 italic text-slate-400 mb-2">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-800">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-slate-600 px-2 py-1 text-left font-semibold text-slate-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-700 px-2 py-1 text-slate-300">{children}</td>
  ),
  hr: () => <hr className="border-slate-700 my-3" />,
};

interface IracStepsProps {
  /** Parsed IRAC sections. Pass null while still streaming. */
  irac: Partial<IracResponse> | null;
  /** Raw accumulated stream text shown while irac is null. */
  streamText?: string;
  loading?: boolean;
}

export function IracSteps({ irac, streamText = "", loading = false }: IracStepsProps) {
  const [activeStep, setActiveStep] = useState<StepKey>("issue");

  return (
    <div>
      {/* Step progress bar */}
      <div className="flex items-center mb-4">
        {IRAC_STEPS.map((step, i) => (
          <div key={step.key} className="flex items-center flex-1">
            <button
              onClick={() => irac?.[step.key] && setActiveStep(step.key)}
              className={cn(
                "flex flex-col items-center gap-1 px-2 py-1 rounded-lg transition-colors w-full",
                activeStep === step.key ? step.color + " border" : "text-slate-600",
                irac?.[step.key] && "cursor-pointer",
              )}
            >
              {step.icon}
              <span className="text-xs font-medium">{step.label}</span>
            </button>
            {i < IRAC_STEPS.length - 1 && (
              <ChevronRight className="h-4 w-4 text-slate-700 shrink-0" />
            )}
          </div>
        ))}
      </div>

      {/* Active step card */}
      {IRAC_STEPS.map((step, i) =>
        activeStep === step.key ? (
          <div
            key={step.key}
            className={cn("rounded-xl border p-4 text-sm text-slate-300", step.color)}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className={step.color.split(" ")[0]}>{step.icon}</span>
              <span className="font-semibold">{step.label}</span>
              <span className="text-xs text-slate-500">— {step.description}</span>
            </div>

            {loading && !irac?.[step.key] ? (
              <div className="flex items-center gap-2 text-slate-500">
                <Spinner className="h-4 w-4" />
                <span>Reasoning…</span>
              </div>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                {irac?.[step.key] ?? streamText}
              </ReactMarkdown>
            )}

            <div className="flex gap-2 mt-3">
              {i > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setActiveStep(IRAC_STEPS[i - 1].key)}
                >
                  ← {IRAC_STEPS[i - 1].label}
                </Button>
              )}
              {i < IRAC_STEPS.length - 1 && irac?.[IRAC_STEPS[i + 1].key] && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="ml-auto"
                  onClick={() => setActiveStep(IRAC_STEPS[i + 1].key)}
                >
                  {IRAC_STEPS[i + 1].label} →
                </Button>
              )}
            </div>
          </div>
        ) : null,
      )}
    </div>
  );
}

export function parseIrac(text: string): Partial<IracResponse> {
  const extract = (label: string) => {
    const re = new RegExp(`##\\s*${label}[\\s\\S]*?\\n([\\s\\S]*?)(?=##|$)`, "i");
    return (re.exec(text)?.[1] ?? "").trim();
  };
  try {
    const parsed = JSON.parse(text) as Partial<IracResponse>;
    if (parsed.issue) return parsed;
  } catch { /* not JSON */ }
  return {
    issue: extract("issue") || text,
    rule: extract("rule"),
    application: extract("application"),
    conclusion: extract("conclusion"),
    citations: [],
  };
}
