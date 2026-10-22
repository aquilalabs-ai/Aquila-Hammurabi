import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { cn } from "./cn";

/**
 * Light preprocessing before markdown parsing.
 * We do NOT convert <br> here — rehype-raw renders HTML tags natively,
 * so <br> inside table cells works correctly without breaking the table structure.
 */
export function preprocess(text: string): string {
  return text;
}

/** Shared ReactMarkdown component map — dark-theme, GFM-aware, with table + link support. */
export const mdComponents: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => (
    <h1 className="text-base font-bold text-slate-200 mb-2 mt-3">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-bold text-slate-200 mb-1.5 mt-2.5">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-slate-300 mb-1 mt-2">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mb-2 leading-relaxed last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>
  ),
  li: ({ children }) => <li className="text-slate-300">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-200">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
  code: ({ children }) => (
    <code className="bg-slate-900 text-amber-300 rounded px-1 py-0.5 text-xs font-mono">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="bg-slate-900 rounded-lg p-3 mb-2 overflow-x-auto text-xs font-mono">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-slate-600 pl-3 italic text-slate-400 mb-2">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-900">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-slate-800">{children}</tbody>,
  tr: ({ children }) => <tr className="even:bg-slate-800/30">{children}</tr>,
  th: ({ children }) => (
    <th className="border border-slate-600 px-2 py-1 text-left font-semibold text-slate-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-700 px-2 py-1 text-slate-300">{children}</td>
  ),
  hr: () => <hr className="border-slate-700 my-3" />,
  del: ({ children }) => (
    <del className="line-through text-slate-500">{children}</del>
  ),
  input: ({ type, checked, disabled }) =>
    type === "checkbox" ? (
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled ?? true}
        readOnly
        className="mr-1.5 accent-amber-400 align-middle"
      />
    ) : null,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-amber-400 hover:underline"
    >
      {children}
    </a>
  ),
};

interface MdProps {
  children: string;
  className?: string;
  /** Optional extra preprocessing step (e.g. URL linkification) applied before rendering. */
  preprocessFn?: (text: string) => string;
}

/**
 * Drop-in ReactMarkdown wrapper with consistent dark-theme rendering.
 * HTML tags (including &lt;br&gt; inside table cells) are rendered natively via rehype-raw.
 */
export function Md({ children, className, preprocessFn }: MdProps) {
  const content = preprocessFn
    ? preprocess(preprocessFn(children))
    : preprocess(children);
  return (
    <div className={cn("text-sm text-slate-300", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
