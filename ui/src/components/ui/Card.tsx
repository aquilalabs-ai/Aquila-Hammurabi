import { cn } from "./cn";

interface CardProps {
  className?: string;
  children: React.ReactNode;
  gold?: boolean;
}

export function Card({ className, children, gold }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-slate-800/60 p-4",
        gold
          ? "border-gold-600/30 bg-gold-950/20"
          : "border-slate-700",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <h3 className={cn("text-sm font-semibold text-slate-200 mb-2", className)}>
      {children}
    </h3>
  );
}
