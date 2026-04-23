import { BookMarked, Trophy, AlertTriangle, TrendingUp, Star, RotateCcw } from "lucide-react";
import { useAppStore } from "../../store/app";
import { Card, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";

export function ProgressTracker() {
  const {
    topicsCovered,
    quizScores,
    flaggedArticles,
    setActiveStudentTab,
    setPendingRetakeQuiz,
  } = useAppStore();

  const avgScore =
    quizScores.length > 0
      ? Math.round(quizScores.reduce((a, s) => a + s.score, 0) / quizScores.length)
      : null;

  const lastQuizzes = [...quizScores]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-4">
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="text-center">
          <BookMarked className="mx-auto mb-1 h-5 w-5 text-blue-400" />
          <p className="text-2xl font-bold text-slate-100">{topicsCovered.length}</p>
          <p className="text-xs text-slate-500">Topics covered</p>
        </Card>
        <Card className="text-center">
          <Trophy className="mx-auto mb-1 h-5 w-5 text-gold-400" />
          <p className="text-2xl font-bold text-slate-100">{avgScore !== null ? `${avgScore}%` : "—"}</p>
          <p className="text-xs text-slate-500">Avg quiz score</p>
        </Card>
        <Card className="text-center">
          <AlertTriangle className="mx-auto mb-1 h-5 w-5 text-amber-400" />
          <p className="text-2xl font-bold text-slate-100">{flaggedArticles.length}</p>
          <p className="text-xs text-slate-500">Flagged articles</p>
        </Card>
      </div>

      {/* Quiz history */}
      {lastQuizzes.length > 0 && (
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <TrendingUp className="h-3.5 w-3.5 text-green-400" />
              Recent Quiz Scores
            </span>
          </CardTitle>
          <div className="space-y-2">
            {lastQuizzes.map((s) => (
              <div key={s.session_id} className="flex items-center gap-2">
                {s.topic && (
                  <span className="text-xs text-slate-500 truncate max-w-[80px]" title={s.topic}>
                    {s.topic}
                  </span>
                )}
                <div className="flex-1 h-1.5 rounded-full bg-slate-700 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      s.score >= 80
                        ? "bg-green-500"
                        : s.score >= 50
                        ? "bg-amber-500"
                        : "bg-red-500"
                    }`}
                    style={{ width: `${s.score}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-slate-400 w-10 text-right">{s.score}%</span>
                <span className="text-xs text-slate-600 w-16">
                  {new Date(s.date).toLocaleDateString()}
                </span>
                {s.questions && s.questions.length > 0 ? (
                  <button
                    onClick={() => {
                      setPendingRetakeQuiz({ questions: s.questions!, topic: s.topic });
                      setActiveStudentTab("quiz");
                    }}
                    title="Retake this quiz"
                    className="text-slate-600 hover:text-gold-400 transition-colors shrink-0"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <span className="w-3.5 shrink-0" />
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Topics covered */}
      {topicsCovered.length > 0 && (
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <BookMarked className="h-3.5 w-3.5 text-blue-400" />
              Topics Covered
            </span>
          </CardTitle>
          <div className="flex flex-wrap gap-1.5">
            {topicsCovered.map((id) => (
              <Badge key={id} variant="gold" className="text-xs">{id}</Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Flagged articles */}
      {flaggedArticles.length > 0 && (
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <Star className="h-3.5 w-3.5 text-amber-400" />
              Flagged for Review
            </span>
          </CardTitle>
          <div className="flex flex-wrap gap-1.5">
            {flaggedArticles.map((id) => (
              <Badge key={id} className="text-xs border-amber-600/30 bg-amber-600/10 text-amber-400">{id}</Badge>
            ))}
          </div>
        </Card>
      )}

      {topicsCovered.length === 0 && quizScores.length === 0 && (
        <div className="text-center text-slate-600 py-8">
          <Trophy className="mx-auto mb-3 h-10 w-10" />
          <p className="text-sm">Start exploring articles and taking quizzes to track your progress</p>
        </div>
      )}
    </div>
  );
}
