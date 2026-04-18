import { useState, useRef } from "react";
import { PenLine, Sparkles, Copy, Check, X } from "lucide-react";
import { post } from "../../api/client";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { Textarea, Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { Card, CardTitle } from "../../components/ui/Card";
import type { DraftResponse } from "../../types/api";

export function DraftingPanel() {
  const { draftingPanelOpen, toggleDraftingPanel } = useAppStore();
  const [prompt, setPrompt] = useState("");
  const [templateType, setTemplateType] = useState("clause");
  const [jurisdiction, setJurisdiction] = useState("FR");
  const [result, setResult] = useState<DraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  if (!draftingPanelOpen) return null;

  const handleDraft = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const res = await post<DraftResponse>("/draft", {
        prompt,
        template_type: templateType,
        jurisdiction,
      });
      setResult(res);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (result) {
      navigator.clipboard.writeText(result.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-96 flex-col border-l border-slate-700 bg-slate-900 shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <PenLine className="h-4 w-4 text-gold-400" />
          Drafting Assistant
        </div>
        <button onClick={toggleDraftingPanel} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Template type</label>
          <select
            value={templateType}
            onChange={(e) => setTemplateType(e.target.value)}
            className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-gold-500 focus:outline-none"
          >
            <option value="clause">Contract Clause</option>
            <option value="memo">Legal Memo</option>
            <option value="pleading">Pleading Fragment</option>
            <option value="nda">NDA</option>
            <option value="employment">Employment Clause</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Jurisdiction</label>
          <Input
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value.toUpperCase())}
            maxLength={5}
            className="uppercase"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Instructions</label>
          <Textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe what you need drafted…&#10;e.g. 'Confidentiality clause with 2-year duration, governing French law'"
            rows={5}
          />
        </div>

        <Button
          variant="primary"
          className="w-full"
          onClick={handleDraft}
          disabled={!prompt.trim() || loading}
        >
          {loading ? <Spinner className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
          Generate Draft
        </Button>

        {result && (
          <Card>
            <div className="flex items-center justify-between mb-2">
              <CardTitle className="mb-0">Generated Draft</CardTitle>
              <Button size="sm" variant="ghost" onClick={handleCopy}>
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-green-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
            <Textarea
              value={result.content}
              onChange={(e) =>
                setResult((r) => r ? { ...r, content: e.target.value } : r)
              }
              rows={12}
              className="text-xs font-mono"
            />
          </Card>
        )}
      </div>
    </div>
  );
}
