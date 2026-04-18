import { Plus, Trash2, Database, ChevronDown, Link2 } from "lucide-react";
import { useState } from "react";
import { useCorpusList, useDeleteCorpus } from "../../api/hooks/useCorpus";
import { useAppStore } from "../../store/app";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Spinner } from "../ui/Spinner";
import { CorpusIngestModal } from "../modals/CorpusIngestModal";
import { CorpusRegisterModal } from "../modals/CorpusRegisterModal";
import type { CorpusSummary } from "../../types/api";

export function CorpusPanel() {
  const [open, setOpen] = useState(true);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const { data: corpora, isLoading } = useCorpusList();
  const { activeCorpusId, setActiveCorpus } = useAppStore();
  const deleteCorpus = useDeleteCorpus();

  const handleRegistered = (corpus: CorpusSummary) => setActiveCorpus(corpus.id);

  return (
    <>
      <div className="border-b border-slate-700">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span className="flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5" />
            Corpora
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
                {corpora?.map((c) => (
                  <li
                    key={c.id}
                    className={cn(
                      "group flex items-center justify-between rounded px-2 py-1.5 cursor-pointer text-xs",
                      activeCorpusId === c.id
                        ? "bg-gold-500/15 text-gold-400"
                        : "text-slate-400 hover:bg-slate-700 hover:text-slate-200",
                    )}
                    onClick={() => setActiveCorpus(c.id)}
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="truncate">{c.name}</span>
                      <span className="text-slate-600 text-[10px]">{c.jurisdiction} · {c.status}</span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteCorpus.mutate(c.id);
                        if (activeCorpusId === c.id) setActiveCorpus(null);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 ml-1 shrink-0"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </li>
                ))}
                {(!corpora || corpora.length === 0) && (
                  <li className="py-1.5 text-center text-xs text-slate-500">No corpora yet</li>
                )}
              </ul>
            )}

            <Button
              size="sm"
              variant="ghost"
              className="mt-1.5 w-full justify-start text-xs text-slate-500 hover:text-gold-400"
              onClick={() => setRegisterOpen(true)}
            >
              <Link2 className="h-3.5 w-3.5" />
              Register existing
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="mt-0.5 w-full justify-start text-xs text-slate-500 hover:text-gold-400"
              onClick={() => setIngestOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Ingest new corpus
            </Button>
          </div>
        )}
      </div>

      <CorpusIngestModal open={ingestOpen} onClose={() => setIngestOpen(false)} />
      <CorpusRegisterModal
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        onRegistered={handleRegistered}
      />
    </>
  );
}
