"use client";

import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-amber-700 underline">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs">{children}</code>
  ),
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-neutral-50">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-neutral-200 px-2 py-1 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-neutral-200 px-2 py-1">{children}</td>,
};

/**
 * Markdown inside a table cell cannot hold a line break, so models reach for a
 * literal <br>. Raw HTML is not rendered here — deliberately, since the text
 * comes from a model — so those tags would otherwise reach the reader as
 * visible "<br>". Turning them into spaces keeps the cell readable without
 * opening a path for arbitrary markup into the DOM.
 */
const HTML_LINE_BREAK = /<br\s*\/?>/gi;

/** Assistant answers: paragraphs, lists and tables. Tabular data is a primary
 *  case — obligation matrices, deadlines, penalty tiers. */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="whitespace-normal leading-relaxed [&_pre]:overflow-x-auto">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text.replace(HTML_LINE_BREAK, " ")}
      </ReactMarkdown>
    </div>
  );
}
