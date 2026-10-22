import { useState } from "react";
import { Search, ChevronRight, ChevronDown, BookOpen, X } from "lucide-react";
import { useSearch } from "../../api/hooks/useResearch";
import { useAppStore } from "../../store/app";
import { Input } from "../../components/ui/Input";
import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";
import { cn } from "../../components/ui/cn";

export function ResearchSidebar() {
  const { researchSidebarOpen, toggleResearchSidebar } = useAppStore();
  const [query, setQuery] = useState("");
  const { data: results, isLoading } = useSearch(query);

  if (!researchSidebarOpen) return null;

  return (
    <aside className="flex w-72 flex-col border-l border-slate-700 bg-slate-900 overflow-hidden shrink-0">
      <div className="flex items-center justify-between border-b border-slate-700 px-3 py-2.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <BookOpen className="h-3.5 w-3.5 text-gold-400" />
          Legal Research
        </div>
        <button onClick={toggleResearchSidebar} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-3 border-b border-slate-700">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
          <Input
            className="pl-8 text-xs"
            placeholder="Search legal corpus…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading && (
          <div className="flex justify-center py-4">
            <Spinner className="h-5 w-5" />
          </div>
        )}
        {results?.map((r) => (
          <SearchResultItem key={r.chunk_id} result={r} />
        ))}
        {results?.length === 0 && query.length > 2 && (
          <p className="text-center text-xs text-slate-600 py-4">No results found</p>
        )}
        {query.length <= 2 && !isLoading && (
          <p className="text-center text-xs text-slate-600 py-4">Type at least 3 characters to search</p>
        )}
      </div>
    </aside>
  );
}

interface SearchResultItemProps {
  result: {
    chunk_id: string;
    article_id: string | null;
    source_type: string;
    content: string;
    score: number;
  };
}

function SearchResultItem({ result }: SearchResultItemProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-lg border border-slate-700/60 bg-slate-800/40 p-2.5 cursor-pointer hover:border-slate-600"
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-start gap-1.5">
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-slate-500 shrink-0 mt-0.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-slate-500 shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            {result.article_id && (
              <Badge variant="gold">{result.article_id}</Badge>
            )}
            <Badge>{result.source_type}</Badge>
            <span className="text-xs text-slate-500 ml-auto">
              {(result.score * 100).toFixed(0)}%
            </span>
          </div>
          <p className={cn("text-xs text-slate-400", !expanded && "line-clamp-2")}>
            {result.content}
          </p>
        </div>
      </div>
    </div>
  );
}
