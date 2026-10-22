import { useState } from "react";
import { ShieldAlert, ChevronDown, ChevronRight, Lightbulb, Link2 } from "lucide-react";
import { useRiskReport, useAnalysisStatus } from "../../api/hooks/useDocuments";
import { useAppStore } from "../../store/app";
import { RiskBadge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";
import type { RiskFlagItem, RiskSeverity } from "../../types/api";

const severityOrder: RiskSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

const severityColors = {
  CRITICAL: "border-l-red-500",
  HIGH: "border-l-orange-500",
  MEDIUM: "border-l-amber-500",
  LOW: "border-l-green-500",
};

export function RiskReportPanel() {
  const { activeDocumentId } = useAppStore();
  const { data: report, isLoading: reportLoading } = useRiskReport(activeDocumentId);
  const { data: analysisStatus } = useAnalysisStatus(activeDocumentId);

  if (!activeDocumentId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-600">
        <ShieldAlert className="mb-3 h-10 w-10" />
        <p className="text-sm">Upload a document to see the risk report</p>
      </div>
    );
  }

  if (analysisStatus?.status === "pending" || analysisStatus?.status === "running") {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-3">
        <Spinner className="h-8 w-8" />
        <p className="text-sm text-slate-400">Analysing document…</p>
      </div>
    );
  }

  if (analysisStatus?.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-2 text-red-400">
        <ShieldAlert className="h-8 w-8" />
        <p className="text-sm">Analysis failed</p>
        {analysisStatus.error && (
          <p className="text-xs text-slate-500 max-w-sm text-center">{analysisStatus.error}</p>
        )}
      </div>
    );
  }

  if (reportLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!report) return null;

  const grouped = severityOrder.reduce<Record<RiskSeverity, RiskFlagItem[]>>(
    (acc, s) => {
      acc[s] = report.flags.filter((f) => f.severity === s);
      return acc;
    },
    { CRITICAL: [], HIGH: [], MEDIUM: [], LOW: [] },
  );

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <Card>
        <div className="grid grid-cols-4 gap-2 text-center">
          {severityOrder.map((s) => (
            <div key={s}>
              <p className="text-lg font-bold text-slate-100">{grouped[s].length}</p>
              <RiskBadge severity={s} />
            </div>
          ))}
        </div>
      </Card>

      {/* Clause list */}
      {severityOrder.map((s) =>
        grouped[s].length > 0 ? (
          <SeverityGroup key={s} severity={s} flags={grouped[s]} />
        ) : null,
      )}
    </div>
  );
}

function SeverityGroup({ severity, flags }: { severity: RiskSeverity; flags: RiskFlagItem[] }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div>
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center gap-2 py-1 text-left"
      >
        <RiskBadge severity={severity} />
        <span className="text-xs text-slate-500">{flags.length} clause{flags.length !== 1 ? "s" : ""}</span>
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 text-slate-600 ml-auto" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-slate-600 ml-auto" />
        )}
      </button>
      {!collapsed && (
        <div className="mt-1 space-y-2">
          {flags.map((flag, i) => (
            <RiskClauseCard key={i} flag={flag} severity={severity} />
          ))}
        </div>
      )}
    </div>
  );
}

function RiskClauseCard({ flag, severity }: { flag: RiskFlagItem; severity: RiskSeverity }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        "rounded-lg border border-slate-700 bg-slate-800/60 border-l-4 p-3 space-y-2",
        severityColors[severity],
      )}
    >
      <div
        className="cursor-pointer flex items-start justify-between gap-2"
        onClick={() => setExpanded((v) => !v)}
      >
        <p className="text-xs text-slate-300 line-clamp-2">{flag.clause_text}</p>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-slate-500 shrink-0 transition-transform mt-0.5",
            expanded && "rotate-180",
          )}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-slate-500">{flag.risk_type}</span>
      </div>

      {expanded && (
        <div className="space-y-2 pt-1 border-t border-slate-700">
          <div className="flex gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-slate-500 shrink-0 mt-0.5" />
            <p className="text-xs text-slate-400">{flag.explanation}</p>
          </div>
          {flag.suggested_improvement && (
            <div className="flex gap-2">
              <Lightbulb className="h-3.5 w-3.5 text-gold-400 shrink-0 mt-0.5" />
              <p className="text-xs text-gold-300/80">{flag.suggested_improvement}</p>
            </div>
          )}
          {flag.governing_articles.length > 0 && (
            <div className="flex flex-wrap gap-1 items-center">
              <Link2 className="h-3 w-3 text-slate-600" />
              {flag.governing_articles.map((a) => (
                <span
                  key={a}
                  className="text-xs text-gold-400/70 border border-gold-600/20 rounded px-1 py-0.5 bg-gold-950/20"
                >
                  {a}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
