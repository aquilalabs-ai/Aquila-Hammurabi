import { ShieldCheck, AlertTriangle, Info } from "lucide-react";
import { useRiskReport } from "../../api/hooks/useDocuments";
import { useAppStore } from "../../store/app";
import { Card, CardTitle } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import type { RiskSeverity } from "../../types/api";

const FRIENDLY_LABELS: Record<RiskSeverity, { label: string; emoji: string; color: string }> = {
  CRITICAL: { label: "Danger! Read carefully", emoji: "🚨", color: "text-red-400" },
  HIGH: { label: "Important concern", emoji: "⚠️", color: "text-orange-400" },
  MEDIUM: { label: "Worth discussing", emoji: "⚡", color: "text-amber-400" },
  LOW: { label: "Minor note", emoji: "ℹ️", color: "text-green-400" },
};

const RISK_TYPE_EXPLANATIONS: Record<string, string> = {
  liability: "This clause decides who pays if something goes wrong.",
  termination: "This clause describes when and how the contract can be ended.",
  indemnification: "This means one party promises to pay the other's costs or losses.",
  "ip transfer": "Intellectual property changes hands — who owns the ideas or work?",
  "non-compete": "One party agrees not to work for competitors — check the scope!",
  governing_law: "Which country's laws apply if there is a dispute.",
  arbitration: "Instead of going to court, disputes go to a private judge.",
  force_majeure: "What happens if something out of everyone's control occurs.",
};

export function SimplifiedRiskReport() {
  const { activeDocumentId } = useAppStore();
  const { data: report, isLoading } = useRiskReport(activeDocumentId);

  if (!activeDocumentId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-600">
        <ShieldCheck className="mb-3 h-10 w-10" />
        <p className="text-sm">Upload a document to see a plain-language risk summary</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!report || report.flags.length === 0) {
    return (
      <div className="text-center text-slate-600 py-8">
        <ShieldCheck className="mx-auto mb-3 h-10 w-10 text-green-400" />
        <p className="text-sm text-green-400">No significant risks detected!</p>
      </div>
    );
  }

  const critical = report.flags.filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH");
  const moderate = report.flags.filter((f) => f.severity === "MEDIUM");
  const minor = report.flags.filter((f) => f.severity === "LOW");

  return (
    <div className="space-y-4">
      {/* Plain-language summary */}
      <Card gold>
        <CardTitle>What this report means for you</CardTitle>
        <p className="text-sm text-slate-300">
          We found <strong className="text-slate-100">{report.flags.length}</strong> clauses that deserve attention.
          {critical.length > 0 && (
            <> <span className="text-red-400">{critical.length} are serious</span> and you should ask a lawyer to explain them before signing.</>
          )}
          {moderate.length > 0 && (
            <> <span className="text-amber-400">{moderate.length} are worth discussing</span> with the other party.</>
          )}
          {minor.length > 0 && (
            <> <span className="text-green-400">{minor.length} are minor notes</span> you can keep in mind.</>
          )}
        </p>
      </Card>

      {/* Flags as friendly cards */}
      {report.flags.map((flag, i) => {
        const friendly = FRIENDLY_LABELS[flag.severity];
        const typeExplanation = RISK_TYPE_EXPLANATIONS[flag.risk_type.toLowerCase()];

        return (
          <div
            key={i}
            className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 space-y-2"
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{friendly.emoji}</span>
              <span className={`text-sm font-semibold ${friendly.color}`}>{friendly.label}</span>
            </div>

            {typeExplanation && (
              <div className="flex items-start gap-2">
                <Info className="h-3.5 w-3.5 text-blue-400 shrink-0 mt-0.5" />
                <p className="text-xs text-blue-300/80">{typeExplanation}</p>
              </div>
            )}

            <p className="text-xs text-slate-500 italic line-clamp-2">"{flag.clause_text}"</p>

            <div className="flex items-start gap-2">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-slate-300">{flag.explanation}</p>
            </div>

            {flag.suggested_improvement && (
              <div className="rounded-lg bg-green-950/30 border border-green-800/30 p-2.5 text-xs text-green-300">
                💡 <strong>Suggestion:</strong> {flag.suggested_improvement}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
