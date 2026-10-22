import { CorpusPanel } from "./CorpusPanel";
import { SessionsPanel } from "./SessionsPanel";
import { useAppStore } from "../../store/app";

export function Sidebar() {
  const { mode } = useAppStore();

  return (
    <aside className="flex w-56 flex-col border-r border-slate-700 bg-slate-900 overflow-y-auto shrink-0">
      <CorpusPanel />
      {mode === "professional" && <SessionsPanel />}
    </aside>
  );
}
