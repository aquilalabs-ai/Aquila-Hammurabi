import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Send, ChevronDown, ChevronRight, BookOpen, Gavel, FileText, CheckCircle2 } from "lucide-react";
import { Md } from "../../components/ui/Markdown";
import { sseStream } from "../../api/client";
import {
  useSessionMessages,
  useGlobalSessionMessages,
  useCreateGlobalSession,
  globalSessionKeys,
} from "../../api/hooks/useCorpus";
import { useAppStore } from "../../store/app";
import type { StoredMessage } from "../../types/api";
import { Button } from "../../components/ui/Button";
import { Textarea } from "../../components/ui/Input";
import { Badge } from "../../components/ui/Badge";
import { cn } from "../../components/ui/cn";
import { Spinner } from "../../components/ui/Spinner";
import type { IracResponse, Citation } from "../../types/api";


interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  irac?: IracResponse;
  streaming?: boolean;
}

function toMessages(stored: StoredMessage[]): Message[] {
  return stored
    .filter((m) => m.content.trim() !== "")
    .map((m) => {
      const role = m.role === "human" ? "user" : "assistant";
      const content = m.content;
      return {
        id: crypto.randomUUID(),
        role,
        content,
        irac: role === "assistant" ? tryParseIrac(content) : undefined,
      };
    });
}

export function ChatPanel() {
  const { activeCorpusId, activeSessionId, setActiveSession } = useAppStore();
  const qc = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  // Synchronous lock — prevents double-send when the user holds Enter or
  // double-clicks before React has committed the streaming=true state update.
  const submittingRef = useRef(false);

  const isGlobal = !activeCorpusId;

  // Corpus session messages
  const { data: corpusMessages } = useSessionMessages(activeCorpusId, activeSessionId);
  // Global session messages
  const { data: globalMessages } = useGlobalSessionMessages(
    isGlobal ? activeSessionId : null,
  );
  // Auto-create global session on first send
  const createGlobalSession = useCreateGlobalSession();

  // Sync local messages with the server state whenever the active session or its
  // data changes.  A single effect avoids the race where a second effect fires
  // after the first and clears messages that were just populated from the cache
  // (which would never re-trigger with staleTime: Infinity).
  useEffect(() => {
    const stored: StoredMessage[] | undefined = isGlobal ? globalMessages : corpusMessages;
    if (stored === undefined) {
      setMessages([]);
    } else {
      setMessages(toMessages(stored));
    }
  }, [activeSessionId, activeCorpusId, corpusMessages, globalMessages, isGlobal]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async () => {
    if (!input.trim() || submittingRef.current) return;
    submittingRef.current = true;

    // Resolve (or create) the session ID without updating the store yet.
    // Calling setActiveSession before the stream starts would trigger the sync
    // effect which clears local messages, wiping the optimistic UI.
    let sessionId = activeSessionId;
    let pendingSessionId: string | null = null;
    if (isGlobal && !sessionId) {
      try {
        const session = await createGlobalSession.mutateAsync(undefined);
        sessionId = session.session_id;
        pendingSessionId = session.session_id;
      } catch {
        // Session creation failed — proceed without one; the backend will
        // generate a random ID and chat still works without persistence.
      }
    }

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input };
    const assistantId = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      userMsg,
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    setStreaming(true);

    const endpoint = activeCorpusId ? `/corpus/${activeCorpusId}/chat` : "/chat";
    let acc = "";

    // 3-minute safety valve — aborts the stream and resets state if the
    // backend never sends [DONE] (e.g. LLM timeout, network drop).
    const streamTimeout = setTimeout(() => {
      cancelRef.current?.();
    }, 3 * 60_000);

    const finalize = (resolvedId: string | null, pendingId: string | null) => {
      clearTimeout(streamTimeout);
      submittingRef.current = false;
      if (resolvedId) {
        if (activeCorpusId) {
          qc.invalidateQueries({ queryKey: ["session-messages", activeCorpusId, resolvedId] });
        } else {
          qc.invalidateQueries({ queryKey: globalSessionKeys.messages(resolvedId) });
        }
      }
      if (pendingId) setActiveSession(pendingId);
    };

    cancelRef.current = sseStream(
      endpoint,
      { message: input, session_id: sessionId, stream: true },
      (token) => {
        acc += token;
        setMessages((m) =>
          m.map((msg) => (msg.id === assistantId ? { ...msg, content: acc } : msg)),
        );
      },
      () => {
        const irac = tryParseIrac(acc);
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, content: acc, irac, streaming: false }
              : msg,
          ),
        );
        setStreaming(false);
        finalize(pendingSessionId ?? sessionId, pendingSessionId);
      },
      (err) => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, content: `Error: ${err}`, streaming: false }
              : msg,
          ),
        );
        setStreaming(false);
        finalize(pendingSessionId ?? sessionId, pendingSessionId);
      },
    );
  }, [input, activeCorpusId, activeSessionId, isGlobal, streaming, createGlobalSession, setActiveSession, qc]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
            <Gavel className="h-10 w-10" />
            <p className="text-sm">
              {activeCorpusId ? "Ask a legal question…" : "Ask a legal question — no corpus needed"}
            </p>
          </div>
        )}
        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserMessage key={msg.id} content={msg.content} />
          ) : (
            <AssistantMessage key={msg.id} msg={msg} />
          ),
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-700 p-3">
        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask a legal question… (Enter to send, Shift+Enter for newline)"
            rows={2}
            className="flex-1"
          />
          <Button
            variant="primary"
            size="sm"
            onClick={send}
            disabled={!input.trim() || streaming}
            className="self-end"
          >
            {streaming ? <Spinner className="h-4 w-4" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-lg rounded-2xl rounded-tr-sm bg-gold-500/20 px-4 py-2.5 text-sm text-slate-200 border border-gold-500/20">
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({ msg }: { msg: Message }) {
  if (msg.irac) {
    return <IracMessage irac={msg.irac} streaming={msg.streaming} />;
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-2xl rounded-2xl rounded-tl-sm bg-slate-800 border border-slate-700 px-4 py-3 text-sm text-slate-200">
        {msg.streaming && msg.content === "" ? (
          <Spinner className="h-4 w-4" />
        ) : (
          <Md>{msg.content}</Md>
        )}
        {msg.streaming && msg.content !== "" && (
          <span className="inline-block w-1.5 h-4 bg-gold-400 animate-pulse ml-0.5 align-middle" />
        )}
      </div>
    </div>
  );
}

function IracMessage({ irac, streaming }: { irac: IracResponse; streaming?: boolean }) {
  return (
    <div className="max-w-2xl space-y-2">
      <IracSection icon={<BookOpen className="h-3.5 w-3.5" />} title="Issue" content={irac.issue} color="text-blue-400" />
      <IracSection icon={<FileText className="h-3.5 w-3.5" />} title="Rule" content={irac.rule} color="text-purple-400" citations={irac.citations} />
      <IracSection icon={<Gavel className="h-3.5 w-3.5" />} title="Application" content={irac.application} color="text-amber-400" />
      <IracSection icon={<CheckCircle2 className="h-3.5 w-3.5" />} title="Conclusion" content={irac.conclusion} color="text-green-400" />
      {streaming && (
        <span className="inline-block w-1.5 h-4 bg-gold-400 animate-pulse ml-1" />
      )}
    </div>
  );
}

function IracSection({
  icon,
  title,
  content,
  color,
  citations,
}: {
  icon: React.ReactNode;
  title: string;
  content: string;
  color: string;
  citations?: Citation[];
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/60 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 hover:bg-slate-700/40"
      >
        <span className={cn(color)}>{icon}</span>
        <span className={cn("text-xs font-semibold uppercase tracking-wide", color)}>{title}</span>
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-slate-600 ml-auto" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-slate-600 ml-auto" />
        )}
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 text-sm text-slate-300">
          <Md>{content}</Md>
          {citations && citations.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {citations.map((c) => (
                <Badge key={c.article_id} variant="gold" onClick={() => {}}>
                  {c.jurisdiction} · {c.code} · {c.article}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function tryParseIrac(text: string): IracResponse | undefined {
  // If the response is a JSON-wrapped IRAC object
  try {
    const parsed = JSON.parse(text);
    if (parsed.issue && parsed.rule && parsed.application && parsed.conclusion) {
      return parsed as IracResponse;
    }
  } catch {
    // not JSON – check markdown headings
  }
  const hasIrac =
    /##\s*issue/i.test(text) &&
    /##\s*rule/i.test(text) &&
    /##\s*application/i.test(text) &&
    /##\s*conclusion/i.test(text);

  if (!hasIrac) return undefined;

  const extract = (label: string) => {
    const re = new RegExp(`##\\s*${label}[\\s\\S]*?\\n([\\s\\S]*?)(?=##|$)`, "i");
    return (re.exec(text)?.[1] ?? "").trim();
  };

  return {
    issue: extract("issue"),
    rule: extract("rule"),
    application: extract("application"),
    conclusion: extract("conclusion"),
    citations: [],
    raw: text,
  };
}
