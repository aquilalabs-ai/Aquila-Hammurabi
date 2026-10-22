import { useState } from "react";
import { X, Link2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { post } from "../../api/client";
import { corpusKeys } from "../../api/hooks/useCorpus";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Spinner } from "../ui/Spinner";
import type { CorpusSummary } from "../../types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onRegistered?: (corpus: CorpusSummary) => void;
}

export function CorpusRegisterModal({ open, onClose, onRegistered }: Props) {
  const [name, setName] = useState("French Civil Code");
  const [jurisdiction, setJurisdiction] = useState("FR");
  const [articleCount, setArticleCount] = useState("");
  const qc = useQueryClient();

  const register = useMutation({
    mutationFn: (body: object) => post<CorpusSummary>("/corpus/register", body),
    onSuccess: (corpus) => {
      qc.invalidateQueries({ queryKey: corpusKeys.all });
      onRegistered?.(corpus);
      onClose();
      setName("");
    },
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-100">Register Existing Corpus</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <p className="text-xs text-slate-500">
            Use this when you've already ingested data directly into Neo4j/Qdrant. This just
            creates a metadata entry so the chat endpoint can find it.
          </p>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Corpus name</label>
            <Input
              placeholder="e.g. French Civil Code"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Jurisdiction</label>
            <Input
              placeholder="FR"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value.toUpperCase())}
              className="uppercase"
              maxLength={5}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Article count <span className="text-slate-600">(optional, for display)</span>
            </label>
            <Input
              type="number"
              placeholder="e.g. 2500"
              value={articleCount}
              onChange={(e) => setArticleCount(e.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-700 px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() =>
              register.mutate({
                name,
                jurisdiction,
                article_count: articleCount ? parseInt(articleCount) : 0,
              })
            }
            disabled={!name || register.isPending}
          >
            {register.isPending ? (
              <Spinner className="h-3.5 w-3.5" />
            ) : (
              <Link2 className="h-3.5 w-3.5" />
            )}
            Register
          </Button>
        </div>
      </div>
    </div>
  );
}
