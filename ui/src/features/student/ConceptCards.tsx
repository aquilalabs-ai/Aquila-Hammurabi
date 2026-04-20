import { useState, useRef, useEffect } from "react";
import { LightbulbIcon, BookOpen, Link2, RefreshCw, AlertCircle, Search } from "lucide-react";
import { Md } from "../../components/ui/Markdown";
import { post } from "../../api/client";
import { useAppStore } from "../../store/app";
import { useArticleAutocomplete } from "../../api/hooks/useResearch";
import { Button } from "../../components/ui/Button";
import { Card, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";
import type { ConceptCard } from "../../types/api";

// ---------------------------------------------------------------------------
// Article ID combobox
// ---------------------------------------------------------------------------

function ArticleCombobox({
  value,
  onChange,
  onSelect,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSelect: (id: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { data: suggestions, isFetching } = useArticleAutocomplete(value);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const items = suggestions ?? [];

  return (
    <div ref={containerRef} className="relative flex-1">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
        <input
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => value.length >= 2 && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && items.length === 0) {
              // Allow manual entry if nothing matches
              setOpen(false);
              onSelect(value.trim());
            }
          }}
          disabled={disabled}
          placeholder="Search article (e.g. 118, civil, fr-civil-1103…)"
          className="w-full rounded-lg border border-slate-600 bg-slate-900 pl-8 pr-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-gold-500 focus:outline-none focus:ring-1 focus:ring-gold-500/30"
          autoComplete="off"
        />
        {isFetching && (
          <Spinner className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
        )}
      </div>

      {open && items.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full max-h-64 overflow-y-auto rounded-lg border border-slate-600 bg-slate-900 shadow-xl">
          {items.map((item) => (
            <li key={item.id}>
              <button
                className="flex w-full flex-col px-3 py-2 text-left hover:bg-slate-700 transition-colors"
                onMouseDown={(e) => {
                  e.preventDefault(); // keep focus on container
                  onChange(item.id);
                  onSelect(item.id);
                  setOpen(false);
                }}
              >
                <span className="text-sm font-mono text-gold-400">{item.id}</span>
                {item.heading && (
                  <span className="text-xs text-slate-400 truncate">{item.heading}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && value.length >= 2 && items.length === 0 && !isFetching && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-xs text-slate-500 shadow-xl">
          No articles found — press Enter to use "{value}" anyway
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConceptCards() {
  const { activeCorpusId, tone, markTopicCovered } = useAppStore();
  const [inputValue, setInputValue] = useState("");
  const [articleId, setArticleId] = useState("");
  const [card, setCard] = useState<ConceptCard | null>(null);
  const [fallbackText, setFallbackText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchCard = async (id?: string) => {
    const target = (id ?? articleId).trim();
    if (!target || !activeCorpusId) return;
    setLoading(true);
    setCard(null);
    setFallbackText(null);
    try {
      const res = await post<{ session_id: string; response: string }>(`/corpus/${activeCorpusId}/chat`, {
        message: `Call statute_lookup("${target}") to retrieve the article, then explain it as a concept card. Return ONLY valid JSON with no markdown fences: {"article_id":"...","heading":"...","plain_explanation":"...","example":"...","analogy":"...","related":[...]}`,
        stream: false,
        mode: "student",
        tone,
      });
      const raw = (res as unknown as { response: string }).response ?? "";
      const stripped = raw.replace(/```(?:json)?\n?/g, "").replace(/```/g, "");
      let parsed: ConceptCard | null = null;
      try {
        parsed = JSON.parse(stripped.trim()) as ConceptCard;
      } catch {
        const match = /\{[\s\S]*\}/.exec(stripped);
        if (match) {
          try { parsed = JSON.parse(match[0]) as ConceptCard; } catch { /* fall through */ }
        }
      }
      if (parsed) {
        setCard(parsed);
        markTopicCovered(target);
      } else {
        setFallbackText(raw);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (id: string) => {
    setArticleId(id);
    fetchCard(id);
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <ArticleCombobox
          value={inputValue}
          onChange={setInputValue}
          onSelect={handleSelect}
          disabled={loading}
        />
        <Button
          variant="primary"
          onClick={() => {
            const target = inputValue.trim();
            if (target) { setArticleId(target); fetchCard(target); }
          }}
          disabled={loading || !inputValue.trim()}
        >
          {loading ? <Spinner className="h-4 w-4" /> : <BookOpen className="h-4 w-4" />}
        </Button>
      </div>

      {card && (
        <ConceptCardView
          card={card}
          onRefresh={() => fetchCard()}
          loading={loading}
        />
      )}

      {fallbackText && !card && (
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
            <CardTitle className="mb-0 text-amber-400">Article not found as concept card</CardTitle>
          </div>
          <Md>{fallbackText}</Md>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card display
// ---------------------------------------------------------------------------

function ConceptCardView({
  card,
  onRefresh,
  loading,
}: {
  card: ConceptCard;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-gold-400">{card.heading}</h3>
          <p className="text-xs text-slate-500">{card.article_id}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={onRefresh} disabled={loading}>
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
        </Button>
      </div>

      <Card>
        <CardTitle>Plain Explanation</CardTitle>
        <p className="text-sm text-slate-300">{card.plain_explanation}</p>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <LightbulbIcon className="h-3.5 w-3.5 text-gold-400" />
              Example
            </span>
          </CardTitle>
          <p className="text-sm text-slate-300">{card.example}</p>
        </Card>
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5 text-blue-400" />
              Analogy
            </span>
          </CardTitle>
          <p className="text-sm text-slate-300">{card.analogy}</p>
        </Card>
      </div>

      {card.related?.length > 0 && (
        <Card>
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <Link2 className="h-3.5 w-3.5 text-purple-400" />
              Related Articles
            </span>
          </CardTitle>
          <div className="flex flex-wrap gap-1.5">
            {card.related.map((id) => (
              <Badge key={id} variant="gold">{id}</Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
