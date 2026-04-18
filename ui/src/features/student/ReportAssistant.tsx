import { useState } from "react";
import { FileText, MessageSquare, GitMerge, Wand2, Download, ArrowRight, RotateCcw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { post } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Input, Textarea } from "../../components/ui/Input";
import { Card, CardTitle } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";
import type { ReportResponse } from "../../types/api";

type ReportTab = "plan" | "critique" | "coherence";
type PlanStep = "topic" | "problematic" | "plan";

const STUDY_LEVELS = ["bachelor", "master", "doctorate", "other"] as const;
type StudyLevel = (typeof STUDY_LEVELS)[number];

const TABS: { key: ReportTab; label: string; icon: React.ReactNode }[] = [
  { key: "plan", label: "Generate Plan", icon: <FileText className="h-3.5 w-3.5" /> },
  { key: "critique", label: "Critique Plan", icon: <MessageSquare className="h-3.5 w-3.5" /> },
  { key: "coherence", label: "Check Coherence", icon: <GitMerge className="h-3.5 w-3.5" /> },
];

const STEP_LABELS: Record<PlanStep, string> = {
  topic: "1 · Topic",
  problematic: "2 · Problematic",
  plan: "3 · Plan",
};

function StepIndicator({ current }: { current: PlanStep }) {
  const steps: PlanStep[] = ["topic", "problematic", "plan"];
  return (
    <div className="flex items-center gap-1 text-xs">
      {steps.map((s, i) => (
        <span key={s} className="flex items-center gap-1">
          {i > 0 && <ArrowRight className="h-3 w-3 text-slate-600" />}
          <span className={cn(
            "rounded px-2 py-0.5 font-medium",
            s === current ? "bg-slate-700 text-slate-100" : "text-slate-500",
          )}>
            {STEP_LABELS[s]}
          </span>
        </span>
      ))}
    </div>
  );
}

export function ReportAssistant() {
  const [tab, setTab] = useState<ReportTab>("plan");

  // ── Shared state ──────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [studyLevel, setStudyLevel] = useState<StudyLevel>("master");

  // ── Plan tab — three-step state ───────────────────────────────────────────
  const [planStep, setPlanStep] = useState<PlanStep>("topic");
  const [topic, setTopic] = useState("");
  const [field, setField] = useState("");
  const [constraints, setConstraints] = useState("");
  // step 2
  const [problematicSuggestions, setProblematicSuggestions] = useState<string | null>(null);
  const [confirmedProblematic, setConfirmedProblematic] = useState("");
  const [planSessionId, setPlanSessionId] = useState<string | null>(null);
  // step 3
  const [planResult, setPlanResult] = useState<string | null>(null);

  // ── Critique tab ──────────────────────────────────────────────────────────
  const [critiqueTopic, setCritiqueTopic] = useState("");
  const [critiqueLevel, setCritiqueLevel] = useState<StudyLevel>("master");
  const [plan, setPlan] = useState("");
  const [critiqueResult, setCritiqueResult] = useState<string | null>(null);

  // ── Coherence tab ─────────────────────────────────────────────────────────
  const [coherenceTopic, setCoherenceTopic] = useState("");
  const [content, setContent] = useState("");
  const [coherenceResult, setCoherenceResult] = useState<string | null>(null);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const clearTab = (t: ReportTab) => {
    setError(null);
    if (t === "plan") {
      setPlanStep("topic");
      setProblematicSuggestions(null);
      setConfirmedProblematic("");
      setPlanResult(null);
      setPlanSessionId(null);
    } else if (t === "critique") {
      setCritiqueResult(null);
    } else {
      setCoherenceResult(null);
    }
  };

  const activeResult =
    tab === "plan" ? planResult : tab === "critique" ? critiqueResult : coherenceResult;
  const activeTopic =
    tab === "plan" ? topic : tab === "critique" ? critiqueTopic : coherenceTopic;

  const exportTxt = () => {
    if (!activeResult) return;
    const label = tab === "plan" ? "plan" : tab === "critique" ? "critique" : "coherence";
    const slug = activeTopic.trim().slice(0, 40).replace(/[^a-z0-9]/gi, "_").toLowerCase();
    const filename = `hammurabi_${label}${slug ? `_${slug}` : ""}.txt`;
    const blob = new Blob([activeResult], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Step 1 → 2 : generate problematic suggestions ────────────────────────
  const handleSuggestProblematics = async () => {
    setLoading(true);
    setError(null);
    setProblematicSuggestions(null);
    setConfirmedProblematic("");
    setPlanResult(null);
    try {
      const data = await post<ReportResponse>("/report/problematic", {
        topic: topic.trim(),
        study_level: studyLevel,
        field: field.trim() || undefined,
      });
      setProblematicSuggestions(data.response);
      setPlanSessionId(data.session_id);
      setPlanStep("problematic");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2 → 3 : generate plan from confirmed problematic ─────────────────
  const handleGeneratePlan = async () => {
    setLoading(true);
    setError(null);
    setPlanResult(null);
    try {
      const data = await post<ReportResponse>("/report/plan", {
        topic: topic.trim(),
        problematic: confirmedProblematic.trim(),
        study_level: studyLevel,
        field: field.trim() || undefined,
        constraints: constraints.trim() || undefined,
        session_id: planSessionId,
      });
      setPlanResult(data.response);
      setPlanStep("plan");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  // ── Critique / Coherence submit ───────────────────────────────────────────
  const handleOtherSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "critique") {
        setCritiqueResult(null);
        const data = await post<ReportResponse>("/report/critique", {
          plan: plan.trim(),
          topic: critiqueTopic.trim() || undefined,
          study_level: critiqueLevel,
        });
        setCritiqueResult(data.response);
      } else {
        setCoherenceResult(null);
        const data = await post<ReportResponse>("/report/coherence", {
          content: content.trim(),
          topic: coherenceTopic.trim() || undefined,
        });
        setCoherenceResult(data.response);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-0.5 rounded-lg bg-slate-800/60 p-0.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); clearTab(t.key); }}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
              tab === t.key ? "bg-slate-700 text-slate-100" : "text-slate-500 hover:text-slate-300",
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* ── PLAN TAB ──────────────────────────────────────────────────────── */}
      {tab === "plan" && (
        <>
          {/* Step indicator */}
          <div className="px-1">
            <StepIndicator current={planStep} />
          </div>

          {/* Step 1 — Topic */}
          <Card>
            <CardTitle>
              {planStep === "topic" ? "Your topic" : (
                <span className="flex items-center justify-between">
                  <span>Topic</span>
                  <button
                    onClick={() => { setPlanStep("topic"); setProblematicSuggestions(null); setPlanResult(null); }}
                    className="flex items-center gap-1 text-xs font-normal text-slate-500 hover:text-slate-300"
                  >
                    <RotateCcw className="h-3 w-3" /> Change
                  </button>
                </span>
              )}
            </CardTitle>

            {planStep === "topic" ? (
              <div className="space-y-3">
                <div>
                  <label className="mb-1.5 block text-xs text-slate-400">
                    Subject given by your supervisor <span className="text-red-400">*</span>
                  </label>
                  <Textarea
                    placeholder="e.g. L'intelligence artificielle et le droit des contrats"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    rows={2}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1.5 block text-xs text-slate-400">Study level</label>
                    <div className="flex flex-wrap gap-1.5">
                      {STUDY_LEVELS.map((l) => (
                        <Button key={l} size="sm"
                          variant={studyLevel === l ? "primary" : "secondary"}
                          onClick={() => setStudyLevel(l)}
                          className="capitalize text-xs"
                        >{l}</Button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs text-slate-400">Field (optional)</label>
                    <Input placeholder="e.g. Droit, Informatique…" value={field}
                      onChange={(e) => setField(e.target.value)} />
                  </div>
                </div>

                <Button variant="primary" className="mt-1 w-full"
                  onClick={handleSuggestProblematics}
                  disabled={loading || topic.trim().length === 0}
                >
                  {loading
                    ? <><Spinner className="h-4 w-4" />Analysing topic…</>
                    : <><Wand2 className="h-4 w-4" />Suggest Problematics</>}
                </Button>
              </div>
            ) : (
              <p className="text-sm text-slate-300">{topic}</p>
            )}
          </Card>

          {/* Step 2 — Problematic suggestions */}
          {problematicSuggestions && planStep !== "topic" && (
            <Card>
              <CardTitle>
                {planStep === "problematic" ? "Choose your problematic" : (
                  <span className="flex items-center justify-between">
                    <span>Problematic</span>
                    <button
                      onClick={() => { setPlanStep("problematic"); setPlanResult(null); }}
                      className="flex items-center gap-1 text-xs font-normal text-slate-500 hover:text-slate-300"
                    >
                      <RotateCcw className="h-3 w-3" /> Change
                    </button>
                  </span>
                )}
              </CardTitle>

              {/* AI suggestions */}
              <div className="mb-4 rounded-md bg-slate-800/50 p-3 prose prose-invert prose-sm max-w-none
                prose-headings:text-slate-200 prose-headings:text-sm prose-strong:text-slate-200
                prose-li:text-slate-300">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{problematicSuggestions}</ReactMarkdown>
              </div>

              {planStep === "problematic" && (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1.5 block text-xs text-slate-400">
                      Your confirmed problematic{" "}
                      <span className="text-slate-600">— pick one above or write your own</span>
                      <span className="text-red-400"> *</span>
                    </label>
                    <Textarea
                      placeholder="Dans quelle mesure… ? / En quoi… ?"
                      value={confirmedProblematic}
                      onChange={(e) => setConfirmedProblematic(e.target.value)}
                      rows={3}
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs text-slate-400">
                      Constraints{" "}
                      <span className="text-slate-600">— page limit, required sections, etc.</span>
                    </label>
                    <Input
                      placeholder="e.g. 80 pages, three main parts required"
                      value={constraints}
                      onChange={(e) => setConstraints(e.target.value)}
                    />
                  </div>

                  <Button variant="primary" className="w-full"
                    onClick={handleGeneratePlan}
                    disabled={loading || confirmedProblematic.trim().length === 0}
                  >
                    {loading
                      ? <><Spinner className="h-4 w-4" />Building plan…</>
                      : <><ArrowRight className="h-4 w-4" />Generate Plan</>}
                  </Button>
                </div>
              )}

              {planStep === "plan" && (
                <p className="text-sm text-slate-300 italic">{confirmedProblematic}</p>
              )}
            </Card>
          )}

          {/* Step 3 — Plan result */}
          {planResult && (
            <Card>
              <div className="mb-3 flex items-center justify-between">
                <CardTitle className="mb-0">Your Plan</CardTitle>
                <Button size="sm" variant="secondary" onClick={exportTxt}>
                  <Download className="h-3.5 w-3.5" />Export .txt
                </Button>
              </div>
              <Markdown>{planResult}</Markdown>
            </Card>
          )}
        </>
      )}

      {/* ── CRITIQUE TAB ──────────────────────────────────────────────────── */}
      {tab === "critique" && (
        <>
          <Card>
            <div className="space-y-3">
              <CardTitle>Critique an existing plan</CardTitle>
              <div>
                <label className="mb-1.5 block text-xs text-slate-400">Topic / problematic</label>
                <Input placeholder="e.g. La responsabilité civile à l'ère du numérique"
                  value={critiqueTopic} onChange={(e) => setCritiqueTopic(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-slate-400">
                  Your plan <span className="text-red-400">*</span>
                </label>
                <Textarea
                  placeholder={"Paste your plan here…\n\nPartie I – …\n  Chapitre 1 – …\nPartie II – …"}
                  value={plan} onChange={(e) => setPlan(e.target.value)} rows={8} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-slate-400">Study level</label>
                <div className="flex flex-wrap gap-1.5">
                  {STUDY_LEVELS.map((l) => (
                    <Button key={l} size="sm"
                      variant={critiqueLevel === l ? "primary" : "secondary"}
                      onClick={() => setCritiqueLevel(l)}
                      className="capitalize text-xs"
                    >{l}</Button>
                  ))}
                </div>
              </div>
            </div>
            <Button variant="primary" className="mt-4 w-full"
              onClick={handleOtherSubmit}
              disabled={loading || plan.trim().length === 0}
            >
              {loading
                ? <><Spinner className="h-4 w-4" />Analysing…</>
                : <><Wand2 className="h-4 w-4" />Critique Plan</>}
            </Button>
          </Card>

          {critiqueResult && (
            <Card>
              <div className="mb-3 flex items-center justify-between">
                <CardTitle className="mb-0">Critique</CardTitle>
                <Button size="sm" variant="secondary" onClick={exportTxt}>
                  <Download className="h-3.5 w-3.5" />Export .txt
                </Button>
              </div>
              <Markdown>{critiqueResult}</Markdown>
            </Card>
          )}
        </>
      )}

      {/* ── COHERENCE TAB ─────────────────────────────────────────────────── */}
      {tab === "coherence" && (
        <>
          <Card>
            <div className="space-y-3">
              <CardTitle>Check coherence of ideas</CardTitle>
              <div>
                <label className="mb-1.5 block text-xs text-slate-400">
                  Central research question / topic
                </label>
                <Input
                  placeholder="e.g. Dans quelle mesure l'IA remet-elle en cause le droit des contrats ?"
                  value={coherenceTopic} onChange={(e) => setCoherenceTopic(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-slate-400">
                  Ideas or sections to analyse <span className="text-red-400">*</span>
                </label>
                <Textarea
                  placeholder="Paste your outline, draft introduction, or list of ideas…"
                  value={content} onChange={(e) => setContent(e.target.value)} rows={8} />
              </div>
            </div>
            <Button variant="primary" className="mt-4 w-full"
              onClick={handleOtherSubmit}
              disabled={loading || content.trim().length === 0}
            >
              {loading
                ? <><Spinner className="h-4 w-4" />Analysing…</>
                : <><Wand2 className="h-4 w-4" />Check Coherence</>}
            </Button>
          </Card>

          {coherenceResult && (
            <Card>
              <div className="mb-3 flex items-center justify-between">
                <CardTitle className="mb-0">Coherence Analysis</CardTitle>
                <Button size="sm" variant="secondary" onClick={exportTxt}>
                  <Download className="h-3.5 w-3.5" />Export .txt
                </Button>
              </div>
              <Markdown>{coherenceResult}</Markdown>
            </Card>
          )}
        </>
      )}

      {/* Error */}
      {error && (
        <Card>
          <p className="text-sm text-red-400">{error}</p>
        </Card>
      )}
    </div>
  );
}

function preprocessMarkdown(text: string): string {
  // 1. Convert HTML line breaks to markdown paragraph breaks
  let md = text.replace(/<br\s*\/?>/gi, "\n\n");

  // 2. Extract numbered source entries of the form:
  //    **[N] Title**
  //    …
  //    Lien : https://url
  const sources = new Map<number, { title: string; url: string }>();
  const sourceRe = /\*\*\[(\d+)\]\s+([^\n*]+?)\*\*[\s\S]*?Lien\s*:\s*(https?:\/\/[^\s\n]+)/g;
  for (const m of md.matchAll(sourceRe)) {
    sources.set(Number(m[1]), { title: m[2].trim(), url: m[3].trim() });
  }

  // 3. Make bare "Lien : https://..." lines into clickable markdown links
  md = md.replace(/Lien\s*:\s*(https?:\/\/[^\s\n]+)/g, (_, url) => `Lien : [${url}](${url})`);

  // 4. Replace inline [N] citations (not preceded by ** which marks a source header)
  //    with a titled markdown link pointing to the source URL
  if (sources.size > 0) {
    md = md.replace(/(?<!\*\*)\[(\d+)\]/g, (match, raw) => {
      const src = sources.get(Number(raw));
      if (!src?.url) return match;
      const label = src.title ? `${raw} – ${src.title}` : raw;
      return `[${label}](${src.url})`;
    });
  }

  return md;
}

function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none text-slate-200
      prose-headings:text-slate-100 prose-headings:font-semibold
      prose-strong:text-slate-100 prose-li:text-slate-300
      prose-code:text-amber-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:rounded
      prose-a:text-amber-400 prose-a:no-underline hover:prose-a:underline">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: ch }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{ch}</a>
          ),
        }}
      >
        {preprocessMarkdown(children)}
      </ReactMarkdown>
    </div>
  );
}
