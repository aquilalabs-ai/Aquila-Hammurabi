import { useState } from "react";
import { Play } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Textarea } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { sseStream } from "../../api/client";
import { useAppStore } from "../../store/app";
import { IracSteps, parseIrac } from "./IracSteps";
import type { IracResponse } from "../../types/api";

export function IRACWalkthrough() {
  const { activeCorpusId, tone } = useAppStore();
  const [question, setQuestion] = useState("");
  const [irac, setIrac] = useState<Partial<IracResponse> | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamText, setStreamText] = useState("");

  const analyze = () => {
    if (!question.trim() || !activeCorpusId) return;
    setLoading(true);
    setIrac(null);
    setStreamText("");

    let acc = "";
    sseStream(
      `/corpus/${activeCorpusId}/chat`,
      {
        message: `Walk me through the IRAC analysis for: ${question}. Use simple language at ${tone} level.`,
        stream: true,
        mode: "student",
        tone,
      },
      (token) => {
        acc += token;
        setStreamText(acc);
      },
      () => {
        setIrac(parseIrac(acc));
        setLoading(false);
      },
      () => setLoading(false),
    );
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-xs font-medium text-slate-400">Legal question or scenario</label>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. 'A party breaches a contract — what are the consequences under French law?'"
          rows={3}
        />
        <Button
          variant="primary"
          onClick={analyze}
          disabled={!question.trim() || loading || !activeCorpusId}
          className="w-full"
        >
          {loading ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          Walk through IRAC
        </Button>
      </div>

      {(irac || loading) && (
        <IracSteps irac={irac} streamText={streamText} loading={loading} />
      )}
    </div>
  );
}
