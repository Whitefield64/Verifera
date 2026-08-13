"use client";

import dynamic from "next/dynamic";
import { BBox } from "@/lib/api";
import HtmlViewer from "./HtmlViewer";
import { UI } from "@/lib/strings";

const PdfViewer = dynamic(() => import("./PdfViewer"), { ssr: false });

export type OpenDoc = { docId: string; format: "pdf" | "html" | "docx"; title: string };

export type ViewerTarget = {
  docId: string;
  page: number | null;
  rects: BBox[];
  quote: string;
  chunkText: string;
  nonce: number;
};

export default function Viewer({
  openDocs,
  activeId,
  target,
  onSelect,
  onClose,
}: {
  openDocs: OpenDoc[];
  activeId: string | null;
  target: ViewerTarget | null;
  onSelect: (docId: string) => void;
  onClose: (docId: string) => void;
}) {
  const active = openDocs.find((d) => d.docId === activeId) ?? null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 overflow-x-auto border-b border-[var(--verifera-line)] bg-[#f7f6fb] px-2 pt-2">
        {openDocs.map((doc) => (
          <div
            key={doc.docId}
            className={`flex shrink-0 cursor-pointer items-center gap-2 rounded-t-lg border border-b-0 px-3 py-1.5 text-xs ${
              doc.docId === activeId
                ? "border-[var(--verifera-line)] bg-white font-medium text-[#21144f]"
                : "border-transparent bg-[var(--verifera-purple-soft)] text-[var(--verifera-ink-muted)] hover:bg-white"
            }`}
            onClick={() => onSelect(doc.docId)}
            title={doc.title}
          >
            <span className="max-w-48 truncate">{doc.docId}</span>
            <span className="rounded bg-neutral-200 px-1 text-[10px] uppercase">{doc.format}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClose(doc.docId);
              }}
              className="text-neutral-400 hover:text-neutral-900"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {!active && (
          <div className="flex h-full items-center justify-center p-8 text-center text-sm text-neutral-400">
            {UI.viewerEmpty[0]}
            <br />
            {UI.viewerEmpty[1]}
          </div>
        )}
        {active && active.format === "pdf" && (
          <PdfViewer
            key={active.docId}
            docId={active.docId}
            target={
              target && target.docId === active.docId && target.page != null
                ? { page: target.page, rects: target.rects, nonce: target.nonce }
                : null
            }
          />
        )}
        {active && active.format !== "pdf" && (
          <HtmlViewer
            key={active.docId}
            docId={active.docId}
            format={active.format}
            target={
              target && target.docId === active.docId
                ? { quote: target.quote, chunkText: target.chunkText, nonce: target.nonce }
                : null
            }
          />
        )}
      </div>
    </div>
  );
}
