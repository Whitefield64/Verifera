"use client";

import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Citation } from "@/lib/api";

function PlainLink({ children, href }: { children?: React.ReactNode; href?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-amber-700 underline">
      {children}
    </a>
  );
}

const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: PlainLink,
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

/**
 * The backend numbers the citations in order of appearance and leaves [[n]] in
 * the prose. Rewriting them into markdown links before parsing is enough to get
 * them through the parser as anchors we can intercept below — much less
 * machinery than a custom mdast node, at the cost of also rewriting a literal
 * [[1]] inside a code span. Answers over a document corpus do not contain one.
 */
export const CITE_MARKER = /\[\[(\d{1,3})\]\]/g;
const CITE_HREF = "#cite-";
export const linkify = (text: string) => text.replace(CITE_MARKER, `[$1](${CITE_HREF}$1)`);

/** Assistant answers: paragraphs, lists, tables and inline citation markers.
 *  Tabular data is a primary case — obligation matrices, deadlines, penalty
 *  tiers. */
export default function Markdown({
  text,
  citations,
  onCitationClick,
}: {
  text: string;
  citations?: Citation[];
  onCitationClick?: (citation: Citation) => void;
}) {
  const byMarker = new Map((citations ?? []).map((c) => [c.marker, c]));
  const withMarkers: Components = {
    ...components,
    a: ({ children, href }) => {
      if (!href?.startsWith(CITE_HREF)) return <PlainLink href={href}>{children}</PlainLink>;
      const number = Number(href.slice(CITE_HREF.length));
      return (
        <CitationMarker
          number={number}
          citation={byMarker.get(number)}
          onClick={onCitationClick}
        />
      );
    },
  };
  return (
    <div className="whitespace-normal leading-relaxed [&_pre]:overflow-x-auto">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={withMarkers}>
        {linkify(text.replace(HTML_LINE_BREAK, " "))}
      </ReactMarkdown>
    </div>
  );
}

/** A footnote number. Inert while the answer streams: the prose carries the
 *  number before the citation list exists, and a marker that opens nothing is
 *  better than a number that appears late and reflows the text under the
 *  reader's eyes. */
function CitationMarker({
  number,
  citation,
  onClick,
}: {
  number: number;
  citation?: Citation;
  onClick?: (citation: Citation) => void;
}) {
  if (!citation || !onClick) {
    return <sup className="ml-0.5 text-[0.65rem] text-neutral-300">{number}</sup>;
  }
  const where = citation.page != null ? ` · p.${citation.page}` : "";
  return (
    <sup className="ml-0.5">
      {/* leading-none is load-bearing: preflight sets line-height:0 on sup so a
          superscript cannot grow the line box, and an inline-block button
          inherits it into a 10x0 hit area. The glyph still paints, so this only
          shows up as clicks that land on nothing. */}
      <button
        onClick={() => onClick(citation)}
        title={`${citation.title ?? citation.doc_id}${where}\n\n${citation.quote}`}
        className={`rounded px-1 py-0.5 text-[0.65rem] font-medium leading-none transition-colors ${
          citation.verified
            ? "text-emerald-700 hover:bg-emerald-100"
            : "text-amber-700 hover:bg-amber-100"
        }`}
      >
        {number}
      </button>
    </sup>
  );
}
