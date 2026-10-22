import { useState, useEffect } from "react";
import {
  HelpCircle,
  CheckCircle2,
  XCircle,
  ChevronRight,
  RefreshCw,
  RotateCcw,
  Trophy,
} from "lucide-react";
import { post } from "../../api/client";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Card, CardTitle } from "../../components/ui/Card";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";
import type { QuizQuestion } from "../../types/api";

function extractJsonArray<T>(raw: string, key: string): T[] {
  const stripped = raw.replace(/```(?:json)?\n?/g, "").replace(/```/g, "");
  const candidates = [stripped, ...stripped.match(/\{[\s\S]*?\}/g) ?? []];
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate.trim()) as Record<string, unknown>;
      if (Array.isArray(parsed[key])) return parsed[key] as T[];
    } catch {
      // try next
    }
  }
  // Last resort: find the outermost {...} block
  const match = /\{[\s\S]*\}/.exec(stripped);
  if (match) {
    try {
      const parsed = JSON.parse(match[0]) as Record<string, unknown>;
      if (Array.isArray(parsed[key])) return parsed[key] as T[];
    } catch {
      // give up
    }
  }
  return [];
}

interface QuizState {
  questions: QuizQuestion[];
  current: number;
  answers: Record<string, string>;
  revealed: Set<string>;
  done: boolean;
}

export function QuizPanel() {
  const { activeCorpusId, tone, addQuizScore, pendingRetakeQuiz, setPendingRetakeQuiz } = useAppStore();
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(5);
  const [loading, setLoading] = useState(false);
  const [quiz, setQuiz] = useState<QuizState | null>(null);

  useEffect(() => {
    if (pendingRetakeQuiz) {
      setQuiz({
        questions: pendingRetakeQuiz.questions,
        current: 0,
        answers: {},
        revealed: new Set(),
        done: false,
      });
      if (pendingRetakeQuiz.topic) setTopic(pendingRetakeQuiz.topic);
      setPendingRetakeQuiz(null);
    }
  }, [pendingRetakeQuiz, setPendingRetakeQuiz]);

  const generateQuiz = async () => {
    if (!activeCorpusId) return;
    setLoading(true);
    setQuiz(null);
    try {
      const res = await post<{ session_id: string; response: string }>(
        `/corpus/${activeCorpusId}/chat`,
        {
          message: `Generate ${count} quiz questions about "${topic || "key legal concepts"}". Mix multiple-choice and open questions. Return ONLY valid JSON with no markdown fences: { "questions": [{"id": "...", "question": "...", "type": "multiple_choice|open", "choices": [...], "correct_answer": "...", "article_id": "..."}] }`,
          stream: false,
          mode: "student",
          tone,
        },
      );
      const raw = (res as unknown as { response: string }).response ?? "";
      const questions = extractJsonArray<QuizQuestion>(raw, "questions");
      if (questions.length > 0) {
        setQuiz({ questions, current: 0, answers: {}, revealed: new Set(), done: false });
      }
    } finally {
      setLoading(false);
    }
  };

  if (quiz?.done) {
    const score = quiz.questions.reduce((acc, q) => {
      const answer = quiz.answers[q.id];
      if (answer && q.correct_answer) {
        return acc + (answer.toLowerCase() === q.correct_answer.toLowerCase() ? 1 : 0);
      }
      return acc + (quiz.revealed.has(q.id) ? 0.5 : 0);
    }, 0);
    const pct = Math.round((score / quiz.questions.length) * 100);

    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <Trophy className="h-12 w-12 text-gold-400" />
        <div className="text-center">
          <p className="text-2xl font-bold text-gold-400">{pct}%</p>
          <p className="text-sm text-slate-400">
            {score.toFixed(1)} / {quiz.questions.length} correct
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              addQuizScore(crypto.randomUUID(), pct, quiz.questions, topic || undefined);
              setQuiz(null);
            }}
          >
            <RefreshCw className="h-4 w-4" />
            New Quiz
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              addQuizScore(crypto.randomUUID(), pct, quiz.questions, topic || undefined);
              setQuiz({
                questions: quiz.questions,
                current: 0,
                answers: {},
                revealed: new Set(),
                done: false,
              });
            }}
          >
            <RotateCcw className="h-4 w-4" />
            Retake
          </Button>
        </div>
      </div>
    );
  }

  if (quiz) {
    const q = quiz.questions[quiz.current];
    const isLast = quiz.current === quiz.questions.length - 1;
    const hasAnswered = !!quiz.answers[q.id] || quiz.revealed.has(q.id);

    const next = () => {
      if (isLast) {
        setQuiz((s) => s && { ...s, done: true });
      } else {
        setQuiz((s) => s && { ...s, current: s.current + 1 });
      }
    };

    return (
      <div className="space-y-4">
        {/* Progress */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">
            Question {quiz.current + 1} / {quiz.questions.length}
          </span>
          <div className="flex-1 h-1.5 rounded-full bg-slate-700 overflow-hidden">
            <div
              className="h-full bg-gold-500 transition-all"
              style={{ width: `${((quiz.current + 1) / quiz.questions.length) * 100}%` }}
            />
          </div>
        </div>

        <Card>
          <div className="flex items-start gap-2 mb-4">
            <HelpCircle className="h-4 w-4 text-gold-400 shrink-0 mt-0.5" />
            <p className="text-sm text-slate-200">{q.question}</p>
          </div>

          {q.type === "multiple_choice" && q.choices && (
            <div className="space-y-2">
              {q.choices.map((choice, i) => {
                const isSelected = quiz.answers[q.id] === choice;
                const isCorrect = q.correct_answer === choice;
                const showResult = hasAnswered;
                return (
                  <button
                    key={i}
                    onClick={() => {
                      if (hasAnswered) return;
                      setQuiz((s) => s && { ...s, answers: { ...s.answers, [q.id]: choice } });
                    }}
                    className={cn(
                      "w-full text-left rounded-lg border px-3 py-2 text-sm transition-colors",
                      !showResult && "border-slate-600 bg-slate-800 hover:border-slate-500",
                      showResult && isCorrect && "border-green-500/50 bg-green-500/10 text-green-300",
                      showResult && isSelected && !isCorrect && "border-red-500/50 bg-red-500/10 text-red-300",
                      showResult && !isSelected && !isCorrect && "border-slate-700 bg-slate-800/40 text-slate-500",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      {showResult && isCorrect && <CheckCircle2 className="h-4 w-4 text-green-400 shrink-0" />}
                      {showResult && isSelected && !isCorrect && <XCircle className="h-4 w-4 text-red-400 shrink-0" />}
                      {choice}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {q.type === "open" && (
            <div className="space-y-2">
              <Input
                placeholder="Your answer…"
                value={quiz.answers[q.id] ?? ""}
                onChange={(e) =>
                  setQuiz((s) =>
                    s && { ...s, answers: { ...s.answers, [q.id]: e.target.value } }
                  )
                }
                disabled={quiz.revealed.has(q.id)}
              />
              {!quiz.revealed.has(q.id) && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    setQuiz((s) =>
                      s && { ...s, revealed: new Set([...s.revealed, q.id]) }
                    )
                  }
                >
                  Reveal Answer
                </Button>
              )}
              {quiz.revealed.has(q.id) && q.correct_answer && (
                <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-2.5 text-xs text-green-300">
                  <strong>Model answer:</strong> {q.correct_answer}
                </div>
              )}
            </div>
          )}
        </Card>

        <Button
          variant="primary"
          className="w-full"
          onClick={next}
          disabled={!hasAnswered}
        >
          {isLast ? "Finish Quiz" : "Next"}
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Generate Quiz</CardTitle>
        <div className="space-y-3">
          <div>
            <label className="mb-1.5 block text-xs text-slate-400">Topic (optional)</label>
            <Input
              placeholder="e.g. contract obligations, civil liability…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-400">Number of questions</label>
            <div className="flex gap-2">
              {[3, 5, 10].map((n) => (
                <Button
                  key={n}
                  size="sm"
                  variant={count === n ? "primary" : "secondary"}
                  onClick={() => setCount(n)}
                >
                  {n}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Button
        variant="primary"
        className="w-full"
        onClick={generateQuiz}
        disabled={loading || !activeCorpusId}
      >
        {loading ? <Spinner className="h-4 w-4" /> : <HelpCircle className="h-4 w-4" />}
        Start Quiz
      </Button>
    </div>
  );
}
