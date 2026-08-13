"use client";

import { useEffect, useRef, useState } from "react";
import Chat, { Message } from "@/components/Chat";
import Viewer, { OpenDoc, ViewerTarget } from "@/components/Viewer";
import { Citation, DocInfo, fetchDocuments, streamChat, ToolEvent } from "@/lib/api";
import { ActivityItem } from "@/lib/activity";
import { fetchPack, FALLBACK_PACK, PackInfo } from "@/lib/pack";

const CHAT_MIN_WIDTH = 320;
const CHAT_DEFAULT_WIDTH = 420;
const CHAT_MAX_WIDTH = 720;
const VIEWER_MIN_WIDTH = 360;

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [openDocs, setOpenDocs] = useState<OpenDoc[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [target, setTarget] = useState<ViewerTarget | null>(null);
  const [pack, setPack] = useState<PackInfo>(FALLBACK_PACK);
  const [chatWidth, setChatWidth] = useState(CHAT_DEFAULT_WIDTH);
  const layoutRef = useRef<HTMLDivElement>(null);
  const docsRef = useRef<Map<string, DocInfo>>(new Map());

  useEffect(() => {
    fetchDocuments()
      .then((docs) => {
        docsRef.current = new Map(docs.map((d) => [d.doc_id, d]));
      })
      .catch(() => {});
    fetchPack().then(setPack);
  }, []);

  async function handleSend(text: string) {
    const history = messages
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", streaming: true },
    ]);
    setBusy(true);
    const pushActivity = (item: ActivityItem) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, activity: [...(last.activity ?? []), item] };
        return next;
      });
    try {
      await streamChat(text, history, {
        onDelta: (delta) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + delta };
            return next;
          }),
        onThinking: (text) => pushActivity({ type: "thinking", text }),
        onTool: (tool: ToolEvent) => pushActivity({ type: "tool", ...tool }),
        onDone: (response) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            const elapsed = response.meta?.["elapsed_ms"];
            next[next.length - 1] = {
              role: "assistant",
              content: response.answer,
              citations: response.citations,
              activity: last.activity,
              elapsedMs: typeof elapsed === "number" ? elapsed : undefined,
            };
            return next;
          }),
      });
    } catch (error) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...last,
          streaming: false,
          error: error instanceof Error ? error.message : String(error),
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  function handleCitationClick(citation: Citation) {
    const info = docsRef.current.get(citation.doc_id);
    const format = info?.format ?? (citation.page != null ? "pdf" : "html");
    setOpenDocs((prev) =>
      prev.some((d) => d.docId === citation.doc_id)
        ? prev
        : [...prev, { docId: citation.doc_id, format, title: citation.doc_id }],
    );
    setActiveId(citation.doc_id);
    const rects = citation.bboxes?.length
      ? citation.bboxes
      : citation.bbox
        ? [{ ...citation.bbox, page: citation.page ?? undefined }]
        : [];
    setTarget({
      docId: citation.doc_id,
      page: citation.page,
      rects,
      quote: citation.quote,
      chunkText: citation.chunk_text,
      nonce: Date.now(),
    });
  }

  function handleClose(docId: string) {
    const next = openDocs.filter((d) => d.docId !== docId);
    setOpenDocs(next);
    if (activeId === docId) setActiveId(next.length ? next[next.length - 1].docId : null);
  }

  function clampChatWidth(width: number) {
    const layoutWidth = layoutRef.current?.getBoundingClientRect().width ?? 0;
    const maxByViewport = layoutWidth ? layoutWidth - VIEWER_MIN_WIDTH : CHAT_MAX_WIDTH;
    const maxWidth = Math.max(
      CHAT_MIN_WIDTH,
      Math.min(CHAT_MAX_WIDTH, maxByViewport),
    );

    return Math.min(Math.max(width, CHAT_MIN_WIDTH), maxWidth);
  }

  function handleResizePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const pointerId = event.pointerId;
    const startX = event.clientX;
    const startWidth = chatWidth;
    const handle = event.currentTarget;

    try {
      handle.setPointerCapture(pointerId);
    } catch {
      // Window listeners below keep resize working when pointer capture is unavailable.
    }
    document.body.classList.add("cursor-col-resize", "select-none");

    function handlePointerMove(moveEvent: PointerEvent) {
      setChatWidth(clampChatWidth(startWidth + moveEvent.clientX - startX));
    }

    function handlePointerUp() {
      if (handle.hasPointerCapture(pointerId)) {
        handle.releasePointerCapture(pointerId);
      }
      document.body.classList.remove("cursor-col-resize", "select-none");
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
  }

  function handleResizeKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const delta = event.shiftKey ? 40 : 16;
    setChatWidth((width) =>
      clampChatWidth(width + (event.key === "ArrowRight" ? delta : -delta)),
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <h1 className="text-sm font-semibold tracking-wide">{pack.heading}</h1>
          {pack.tagline && (
            <span className="text-xs text-neutral-500">{pack.tagline}</span>
          )}
        </div>
        <span className="text-[10px] uppercase tracking-wider text-neutral-400">
          {pack.name}
        </span>
      </header>
      <div ref={layoutRef} className="flex min-h-0 flex-1">
        <div
          className="relative shrink-0 border-r border-neutral-200 bg-neutral-50"
          style={{ width: chatWidth }}
        >
          <Chat
            messages={messages}
            busy={busy}
            pack={pack}
            onSend={handleSend}
            onCitationClick={handleCitationClick}
          />
          <div
            role="separator"
            aria-label="Ridimensiona chat"
            aria-orientation="vertical"
            aria-valuemin={CHAT_MIN_WIDTH}
            aria-valuemax={CHAT_MAX_WIDTH}
            aria-valuenow={Math.round(chatWidth)}
            tabIndex={0}
            onPointerDown={handleResizePointerDown}
            onKeyDown={handleResizeKeyDown}
            className="absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize outline-none after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent hover:after:bg-amber-500 focus:after:bg-amber-500"
          />
        </div>
        <div className="min-w-0 flex-1">
          <Viewer
            openDocs={openDocs}
            activeId={activeId}
            target={target}
            onSelect={setActiveId}
            onClose={handleClose}
          />
        </div>
      </div>
    </div>
  );
}
