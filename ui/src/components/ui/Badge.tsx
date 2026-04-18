import { cn } from "./cn";
import type { RiskSeverity } from "../../types/api";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "gold" | "risk";
  severity?: RiskSeverity;
  onClick?: () => void;
}

const severityClasses: Record<RiskSeverity, string> = {
  CRITICAL: "bg-red-600/20 text-red-400 border-red-600/40",
  HIGH: "bg-orange-600/20 text-orange-400 border-orange-600/40",
  MEDIUM: "bg-amber-600/20 text-amber-400 border-amber-600/40",
  LOW: "bg-green-600/20 text-green-400 border-green-600/40",
};

export function Badge({ children, className, variant = "default", severity, onClick }: BadgeProps) {
  return (
    <span
      onClick={onClick}
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium",
        variant === "default" && "border-slate-600 bg-slate-700 text-slate-300",
        variant === "gold" &&
          "border-gold-600/40 bg-gold-600/15 text-gold-400 cursor-pointer hover:bg-gold-600/25",
        variant === "risk" && severity && severityClasses[severity],
        onClick && "cursor-pointer",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function RiskBadge({ severity }: { severity: RiskSeverity }) {
  return <Badge variant="risk" severity={severity}>{severity}</Badge>;
}
