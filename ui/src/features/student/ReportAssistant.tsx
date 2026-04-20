import { useState } from "react";
import { FileText, MessageSquare, GitMerge, Wand2, Download, ArrowRight, RotateCcw, BookMarked, X, Globe, Database } from "lucide-react";
import { Md } from "../../components/ui/Markdown";
import { post } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Input, Textarea } from "../../components/ui/Input";
import { Card, CardTitle } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";
import type { ReportResponse, ReportSourceItem } from "../../types/api";

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
  const [sources, setSources] = useState<ReportSourceItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

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
    setSources([]);
    setDrawerOpen(false);
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
      setSources(data.sources ?? []);
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
      setSources((prev) => {
        const merged = [...prev];
        for (const s of data.sources ?? []) {
          const dup = s.type === "web"
            ? merged.some((x) => x.url === s.url)
            : merged.some((x) => x.article_id === s.article_id);
          if (!dup) merged.push(s);
        }
        return merged;
      });
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
        setSources(data.sources ?? []);
      } else {
        setCoherenceResult(null);
        const data = await post<ReportResponse>("/report/coherence", {
          content: content.trim(),
          topic: coherenceTopic.trim() || undefined,
        });
        setCoherenceResult(data.response);
        setSources(data.sources ?? []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <SourcesDrawer sources={sources} open={drawerOpen} onClose={() => setDrawerOpen(false)} />

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
              <div className="mb-2 rounded-md bg-slate-800/50 p-3">
                <Md preprocessFn={preprocessMarkdown}>{problematicSuggestions}</Md>
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
                <div className="flex items-center gap-2">
                  {sources.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => setDrawerOpen(true)}>
                      <BookMarked className="h-3.5 w-3.5 text-amber-400" />
                      {sources.length} sources
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" onClick={exportTxt}>
                    <Download className="h-3.5 w-3.5" />Export .txt
                  </Button>
                </div>
              </div>
              <Md preprocessFn={preprocessMarkdown}>{planResult}</Md>
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
                <div className="flex items-center gap-2">
                  {sources.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => setDrawerOpen(true)}>
                      <BookMarked className="h-3.5 w-3.5 text-amber-400" />
                      {sources.length} sources
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" onClick={exportTxt}>
                    <Download className="h-3.5 w-3.5" />Export .txt
                  </Button>
                </div>
              </div>
              <Md preprocessFn={preprocessMarkdown}>{critiqueResult}</Md>
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
                <div className="flex items-center gap-2">
                  {sources.length > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => setDrawerOpen(true)}>
                      <BookMarked className="h-3.5 w-3.5 text-amber-400" />
                      {sources.length} sources
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" onClick={exportTxt}>
                    <Download className="h-3.5 w-3.5" />Export .txt
                  </Button>
                </div>
              </div>
              <Md preprocessFn={preprocessMarkdown}>{coherenceResult}</Md>
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

// ── Sources drawer ────────────────────────────────────────────────────────────

function SourcesDrawer({
  sources,
  open,
  onClose,
}: {
  sources: ReportSourceItem[];
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  const webSources = sources.filter((s) => s.type === "web");
  const kbSources = sources.filter((s) => s.type === "kb");

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l border-slate-700 bg-slate-900 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <BookMarked className="h-4 w-4 text-amber-400" />
          Sources <span className="text-slate-500 font-normal">({sources.length})</span>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Web sources */}
        {webSources.length > 0 && (
          <section>
            <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              <Globe className="h-3.5 w-3.5" /> Sources web ({webSources.length})
            </h3>
            <ul className="space-y-2">
              {webSources.map((s, i) => (
                <li key={i} className="rounded-lg border border-slate-700 bg-slate-800/50 p-2.5">
                  {s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-amber-400 hover:underline text-xs font-medium leading-snug block mb-1"
                    >
                      {s.title}
                    </a>
                  ) : (
                    <p className="text-xs font-medium text-slate-200 mb-1">{s.title}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-slate-500">
                    {s.publication && <span>{s.publication}</span>}
                    {s.publication && s.date && <span>·</span>}
                    {s.date && <span>{s.date}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* KB sources */}
        {kbSources.length > 0 && (
          <section>
            <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              <Database className="h-3.5 w-3.5" /> Base de connaissances ({kbSources.length})
            </h3>
            <ul className="space-y-2">
              {kbSources.map((s, i) => (
                <li key={i} className="rounded-lg border border-slate-700 bg-slate-800/50 p-2.5">
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-mono text-gold-400 shrink-0 mt-0.5 leading-snug">
                      {s.article_id}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-slate-200 leading-snug">{s.title}</p>
                      {s.excerpt && (
                        <p className="text-xs text-slate-500 mt-1 line-clamp-4 leading-relaxed">
                          {s.excerpt}
                        </p>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {sources.length === 0 && (
          <p className="text-xs text-slate-600 text-center pt-4">Aucune source disponible.</p>
        )}
      </div>
    </div>
  );
}

function preprocessMarkdown(text: string): string {
  // <br> tags are intentionally left as-is — rehype-raw renders them natively,
  // which correctly handles <br> inside table cells without breaking the table.
  let md = text;

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

