import { useEffect, useRef, useState } from "react";
import { Scale, Eye, EyeOff, RefreshCw, Play, Wand2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { post, sseStream } from "../../api/client";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Textarea } from "../../components/ui/Input";
import { Card, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";
import { IracSteps, parseIrac } from "./IracSteps";
import type { GenerateCaseResponse, IracResponse } from "../../types/api";

export function CaseSimulation() {
  const { activeCorpusId } = useAppStore();

  // Shared setup inputs
  const [topic, setTopic] = useState("");
  const [scenario, setScenario] = useState("");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");

  // Generate-mode state
  const [generatedCase, setGeneratedCase] = useState<GenerateCaseResponse | null>(null);
  const [studentAnswer, setStudentAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [loadingGenerate, setLoadingGenerate] = useState(false);

  // Shared IRAC result state (used by both modes once streaming completes)
  const [iracResult, setIracResult] = useState<Partial<IracResponse> | null>(null);
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => () => { cancelRef.current?.(); }, []);

  const isSolveMode = scenario.trim().length > 0;

  // ── Stream /simulate and parse IRAC on completion ─────────────────────────
  const streamSolve = (scenarioText: string) => {
    cancelRef.current?.();
    setIracResult(null);
    setStreamText("");
    setStreaming(true);

    let acc = "";
    const cancel = sseStream(
      "/simulate",
      { scenario: scenarioText, legal_domain: topic.trim() || undefined, stream: true },
      (token) => { acc += token; setStreamText(acc); },
      () => { setIracResult(parseIrac(acc)); setStreaming(false); },
      () => setStreaming(false),
    );
    cancelRef.current = cancel;
  };

  // ── Generate mode ─────────────────────────────────────────────────────────
  const generate = async () => {
    setLoadingGenerate(true);
    setGeneratedCase(null);
    setStudentAnswer("");
    setRevealed(false);
    setIracResult(null);
    setStreamText("");
    cancelRef.current?.();
    try {
      const data = await post<GenerateCaseResponse>("/generate-case", {
        topic: topic.trim() || undefined,
        difficulty,
      });
      setGeneratedCase(data);
    } finally {
      setLoadingGenerate(false);
    }
  };

  const handleReveal = () => {
    if (!revealed && !iracResult && generatedCase) {
      streamSolve(generatedCase.scenario);
    }
    setRevealed((v) => !v);
  };

  const handleRefresh = () => {
    setIracResult(null);
    setStreamText("");
    setRevealed(false);
    cancelRef.current?.();
    generate();
  };

  const isLoading = loadingGenerate || streaming;

  return (
    <div className="space-y-4">
      {/* Setup */}
      <Card>
        <CardTitle>Case Simulation</CardTitle>
        <div className="space-y-3">
          <div>
            <label className="mb-1.5 block text-xs text-slate-400">Legal domain</label>
            <Input
              placeholder="e.g. contract breach, tort liability…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs text-slate-400">
              Your case scenario{" "}
              <span className="text-slate-600">— optional. Leave blank to generate one.</span>
            </label>
            <Textarea
              placeholder="Paste or describe the case facts here and the AI will solve it with IRAC analysis…"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              rows={4}
            />
          </div>

          {!isSolveMode && (
            <div>
              <label className="mb-1.5 block text-xs text-slate-400">Difficulty</label>
              <div className="flex gap-2">
                {(["easy", "medium", "hard"] as const).map((d) => (
                  <Button
                    key={d}
                    size="sm"
                    variant={difficulty === d ? "primary" : "secondary"}
                    onClick={() => setDifficulty(d)}
                    className="capitalize"
                  >
                    {d}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>

        <Button
          variant="primary"
          className="mt-3 w-full"
          onClick={isSolveMode ? () => streamSolve(scenario.trim()) : generate}
          disabled={isLoading || (!activeCorpusId && !isSolveMode)}
        >
          {isLoading ? (
            <Spinner className="h-4 w-4" />
          ) : isSolveMode ? (
            <Wand2 className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {isSolveMode ? "Solve Scenario" : "Generate Case"}
        </Button>
      </Card>

      {/* ── Solve mode results ─────────────────────────────────────────────── */}
      {isSolveMode && (streamText || streaming) && (
        <>
          <Card gold>
            <div className="flex items-center gap-2 mb-2">
              <Scale className="h-4 w-4 text-gold-400" />
              <CardTitle className="mb-0">Your Scenario</CardTitle>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {scenario}
            </p>
          </Card>

          <Card>
            <div className="flex items-center gap-2 mb-3">
              <CardTitle className="mb-0">
                <span className="text-green-400">IRAC Analysis</span>
              </CardTitle>
              {streaming && <Spinner className="h-3.5 w-3.5 ml-auto" />}
            </div>
            <IracSteps irac={iracResult} streamText={streamText} loading={streaming} />
          </Card>
        </>
      )}

      {/* ── Generate mode results ──────────────────────────────────────────── */}
      {!isSolveMode && generatedCase && (
        <>
          <Card gold>
            <div className="flex items-center gap-2 mb-2">
              <Scale className="h-4 w-4 text-gold-400" />
              <CardTitle className="mb-0">Case Scenario</CardTitle>
              <Badge className="ml-auto capitalize">{generatedCase.difficulty}</Badge>
            </div>
            <div className="text-sm text-slate-300 leading-relaxed prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{generatedCase.scenario}</ReactMarkdown>
            </div>
            {generatedCase.relevant_articles.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="text-xs text-slate-500 mr-1">Hint:</span>
                {generatedCase.relevant_articles.map((a) => (
                  <Badge key={a} variant="gold">{a}</Badge>
                ))}
              </div>
            )}
          </Card>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">
              Your legal analysis
            </label>
            <Textarea
              value={studentAnswer}
              onChange={(e) => setStudentAnswer(e.target.value)}
              placeholder="Apply the IRAC method: identify the issue, state the rule, apply it to the facts, conclude…"
              rows={5}
              disabled={revealed}
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant={revealed ? "secondary" : "primary"}
              onClick={handleReveal}
              disabled={streaming}
              className="flex-1"
            >
              {streaming ? (
                <><Spinner className="h-4 w-4" />Analysing…</>
              ) : revealed ? (
                <><EyeOff className="h-4 w-4" />Hide Model Answer</>
              ) : (
                <><Eye className="h-4 w-4" />Reveal Model Answer</>
              )}
            </Button>
            <Button variant="ghost" onClick={handleRefresh} disabled={isLoading}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>

          {revealed && (iracResult || streaming) && (
            <Card>
              <CardTitle>
                <span className="text-green-400">Model Answer</span>
              </CardTitle>
              <IracSteps irac={iracResult} streamText={streamText} loading={streaming} />
            </Card>
          )}

          {revealed && !iracResult && !streaming && (
            <Card>
              <p className="text-sm text-slate-500">No model answer available.</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
