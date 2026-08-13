"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { docFileUrl, docTextUrl } from "@/lib/api";
import { locateCitation } from "@/lib/anchors";
import Markdown from "@/components/Markdown";
import { UI } from "@/lib/strings";

// Below this the page has effectively no visible content: it happens with
// Next.js App Router pages that serialize their markup into inert <template>
// elements and activate it with client-side JS — with scripts disabled (the
// sandbox's security boundary) that content never reaches the screen.
const MIN_VISIBLE_CHARS = 40;

export type TextTarget = { quote: string; chunkText: string; nonce: number };

const HIGHLIGHT_STYLE_ID = "citation-highlight-style";
const HIGHLIGHT_CSS = "::highlight(citation){background-color:rgba(251,191,36,.55)}";

// The stored original is served untouched into a sandboxed iframe. The sandbox —
// deliberately WITHOUT allow-scripts — is the security boundary: the page's own
// markup can't run scripts/trackers, submit forms, or navigate our tab. Yet it
// still renders pixel-faithfully, because the browser natively honours the page's
// <base href> to load its real CSS/images and resolve its links (an in-page
// re-render into a shadow root loses all of this). allow-same-origin lets us reach
// into the document to paint the citation highlight; allow-popups(+escape) lets a
// clicked link open in a real, un-sandboxed browser tab.
const SANDBOX = "allow-same-origin allow-popups allow-popups-to-escape-sandbox";

/** Renders the original HTML (or mammoth-converted DOCX) in a sandboxed iframe and
 *  highlights the cited passage by scripting into the same-origin frame document. */
export default function HtmlViewer({
  docId,
  format,
  target,
}: {
  docId: string;
  format: "html" | "docx";
  target: TextTarget | null;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [srcDoc, setSrcDoc] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [anchorMiss, setAnchorMiss] = useState(false);
  // undefined = non ancora controllato, null = rendering ok (nessun fallback), string = testo di ripiego
  const [fallbackText, setFallbackText] = useState<string | null | undefined>(undefined);

  // parent keys this component by docId, so docId/format are fixed for its lifetime
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(docFileUrl(docId));
        if (!res.ok) throw new Error(String(res.status));
        let html: string;
        if (format === "docx") {
          const mammoth = (await import("mammoth")).default;
          html = (await mammoth.convertToHtml({ arrayBuffer: await res.arrayBuffer() })).value;
        } else {
          html = await res.text();
        }
        if (!cancelled) setSrcDoc(html);
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [docId, format]);

  const applyHighlight = useCallback(() => {
    const doc = iframeRef.current?.contentDocument;
    const win = iframeRef.current?.contentWindow as (Window & typeof globalThis) | null;
    if (!doc || !win) return;
    win.CSS?.highlights?.delete("citation");
    if (!target) {
      setAnchorMiss(false);
      return;
    }

    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) =>
        node.parentElement?.closest("style,script,noscript")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT,
    });
    const textNodes: Text[] = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode as Text);

    const match = locateCitation(
      textNodes.map((n) => n.data),
      target.quote,
      target.chunkText,
    );
    setAnchorMiss(!match);
    if (!match) return;

    const range = doc.createRange();
    range.setStart(textNodes[match.start.block], match.start.offset);
    range.setEnd(textNodes[match.end.block], match.end.offset);
    if (win.CSS?.highlights && win.Highlight) {
      win.CSS.highlights.set("citation", new win.Highlight(range));
    }
    range.startContainer.parentElement?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target]);

  const onFrameLoad = () => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) {
      setStatus("error");
      return;
    }
    doc.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href") || "";
      // in-page #fragments drive tab widgets whose JS we don't run; scroll to the
      // target within the frame instead of resolving against <base> (which would
      // jump to the site homepage). Everything else opens in a new browser tab.
      if (href.startsWith("#")) {
        a.addEventListener("click", (event) => {
          event.preventDefault();
          doc.getElementById(href.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } else {
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
      }
    });
    if (!doc.getElementById(HIGHLIGHT_STYLE_ID)) {
      const style = doc.createElement("style");
      style.id = HIGHLIGHT_STYLE_ID;
      style.textContent = HIGHLIGHT_CSS;
      (doc.head || doc.documentElement).appendChild(style);
    }
    // Some pages (Next.js App Router among them) serialize their markup into
    // inert <template> elements and only activate it with client-side JS, which
    // we deliberately do not run: the document "loads" with nothing to see.
    if ((doc.body?.innerText ?? "").trim().length < MIN_VISIBLE_CHARS) {
      fetch(docTextUrl(docId))
        .then((res) => (res.ok ? res.text() : Promise.reject(new Error(String(res.status)))))
        .then(setFallbackText)
        .catch(() => setFallbackText(null));
    } else {
      setFallbackText(null);
    }
    setStatus("ready");
  };

  // (re)apply the highlight when the frame becomes ready or the citation changes;
  // deferred a frame so the framed document's layout has settled before we scroll
  useEffect(() => {
    if (status !== "ready") return;
    const raf = requestAnimationFrame(applyHighlight);
    return () => cancelAnimationFrame(raf);
  }, [status, applyHighlight]);

  return (
    <div className="relative h-full w-full bg-white">
      {srcDoc !== null && (
        <iframe
          ref={iframeRef}
          title={docId}
          srcDoc={srcDoc}
          sandbox={SANDBOX}
          onLoad={onFrameLoad}
          className="h-full w-full border-0"
        />
      )}
      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center bg-white text-sm text-neutral-500">
          {UI.docLoading}
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex items-center justify-center bg-white text-sm text-red-600">
          {UI.pdfError}
        </div>
      )}
      {status === "ready" && anchorMiss && target && !fallbackText && (
        <div className="absolute inset-x-0 top-0 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          {UI.passageNotFound}
          “{target.quote.slice(0, 160)}”
        </div>
      )}
      {status === "ready" && fallbackText && (
        <div className="absolute inset-0 overflow-y-auto bg-white">
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
            {UI.scriptsBlocked}
            {target && (
              <div className="mt-1">
                {UI.citedPassage} “{target.quote.slice(0, 160)}”
              </div>
            )}
          </div>
          <div className="p-4 text-sm">
            <Markdown text={fallbackText} />
          </div>
        </div>
      )}
    </div>
  );
}
