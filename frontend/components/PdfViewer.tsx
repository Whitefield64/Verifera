"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { BBox, docFileUrl } from "@/lib/api";
import { UI } from "@/lib/strings";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

export type PdfTarget = { page: number; rects: BBox[]; nonce: number };

export default function PdfViewer({
  docId,
  target,
}: {
  docId: string;
  target: PdfTarget | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [numPages, setNumPages] = useState(0);
  const firstRectRef = useRef<HTMLDivElement>(null);
  const renderedPages = useRef<Set<number>>(new Set());

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth - 32));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // scroll once the target page's canvas exists (it may still be rendering)
  useEffect(() => {
    if (target && renderedPages.current.has(target.page)) scrollToRect();
  }, [target]);

  function scrollToRect() {
    firstRectRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const pageWidth = Math.max(width, 200);

  return (
    <div ref={containerRef} className="h-full overflow-y-auto bg-neutral-100 p-4">
      <Document
        file={docFileUrl(docId)}
        onLoadSuccess={(doc) => setNumPages(doc.numPages)}
        loading={<Notice>{UI.pdfLoading}</Notice>}
        error={<Notice>{UI.pdfError}</Notice>}
      >
        <div className="mx-auto space-y-4" style={{ width: pageWidth }}>
          {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNumber) => {
            const rects =
              target?.rects.filter((r) => (r.page ?? target.page) === pageNumber) ?? [];
            return (
              <div
                key={pageNumber}
                className="relative shadow"
                style={{ minHeight: pageWidth * 1.3 }}
              >
                <Page
                  pageNumber={pageNumber}
                  width={pageWidth}
                  renderTextLayer={false}
                  renderAnnotationLayer={false}
                  onRenderSuccess={() => {
                    renderedPages.current.add(pageNumber);
                    if (target?.page === pageNumber) scrollToRect();
                  }}
                />
                {rects.map((rect, i) => {
                  const scale = pageWidth / rect.page_w;
                  return (
                    <div
                      key={`${target?.nonce}-${i}`}
                      ref={i === 0 ? firstRectRef : undefined}
                      className="citation-highlight pointer-events-none absolute"
                      style={{
                        left: rect.x * scale,
                        top: rect.y * scale,
                        width: rect.w * scale,
                        height: rect.h * scale,
                      }}
                    />
                  );
                })}
                <div className="absolute bottom-1 right-2 rounded bg-black/40 px-1.5 text-[10px] text-white">
                  {pageNumber}
                </div>
              </div>
            );
          })}
        </div>
      </Document>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <div className="p-8 text-center text-sm text-neutral-500">{children}</div>;
}
