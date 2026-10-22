import { Plus, Trash2, MessageSquare, ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  useCorpusSessions,
  useCreateSession,
  useDeleteSession,
  useGlobalSessions,
  useCreateGlobalSession,
  useDeleteGlobalSession,
} from "../../api/hooks/useCorpus";
import { useAppStore } from "../../store/app";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Spinner } from "../ui/Spinner";

export function SessionsPanel() {
  const [open, setOpen] = useState(true);
  const { activeCorpusId, activeSessionId, setActiveSession } = useAppStore();

  // Corpus sessions
  const { data: corpusSessions, isLoading: corpusLoading } = useCorpusSessions(activeCorpusId);
  const createCorpusSession = useCreateSession(activeCorpusId ?? "");
  const deleteCorpusSession = useDeleteSession(activeCorpusId ?? "");

  // Global sessions
  const { data: globalSessions, isLoading: globalLoading } = useGlobalSessions();
  const createGlobalSession = useCreateGlobalSession();
  const deleteGlobalSession = useDeleteGlobalSession();

  const isGlobal = !activeCorpusId;
  const sessions = isGlobal ? globalSessions : corpusSessions;
  const isLoading = isGlobal ? globalLoading : corpusLoading;

  const handleCreate = () => {
    if (isGlobal) {
      createGlobalSession.mutate(undefined, {
        onSuccess: (s) => setActiveSession(s.session_id),
      });
    } else {
      createCorpusSession.mutate(undefined, {
        onSuccess: (s) => setActiveSession(s.session_id),
      });
    }
  };

  const handleDelete = (sessionId: string) => {
    if (isGlobal) {
      deleteGlobalSession.mutate(sessionId);
    } else {
      deleteCorpusSession.mutate(sessionId);
    }
    if (activeSessionId === sessionId) setActiveSession(null);
  };

  const isPending = isGlobal ? createGlobalSession.isPending : createCorpusSession.isPending;

  const label = (s: { session_id: string; title?: string }) =>
    s.title?.trim() || `Session ${s.session_id.slice(0, 6)}`;

  return (
    <div className="border-b border-slate-700">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
      >
        <span className="flex items-center gap-1.5">
          <MessageSquare className="h-3.5 w-3.5" />
          {isGlobal ? "Global Sessions" : "Sessions"}
        </span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="pb-2 px-2">
          {isLoading ? (
            <div className="flex justify-center py-3">
              <Spinner className="h-4 w-4" />
            </div>
          ) : (
            <ul className="space-y-0.5">
              {sessions?.map((s) => (
                <li
                  key={s.session_id}
                  className={cn(
                    "group flex items-center justify-between rounded px-2 py-1.5 cursor-pointer text-xs",
                    activeSessionId === s.session_id
                      ? "bg-gold-500/15 text-gold-400"
                      : "text-slate-400 hover:bg-slate-700 hover:text-slate-200",
                  )}
                  onClick={() => setActiveSession(s.session_id)}
                >
                  <span className="truncate">{label(s)}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(s.session_id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 ml-1 shrink-0"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
              {(!sessions || sessions.length === 0) && (
                <li className="py-1.5 text-center text-xs text-slate-500">No sessions yet</li>
              )}
            </ul>
          )}

          <Button
            size="sm"
            variant="ghost"
            className="mt-1.5 w-full justify-start text-xs text-slate-500 hover:text-gold-400"
            onClick={handleCreate}
            disabled={isPending}
          >
            {isPending ? <Spinner className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
            New session
          </Button>
        </div>
      )}
    </div>
  );
}
