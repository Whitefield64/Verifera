"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Citation } from "@/lib/api";
import { ActivityItem } from "@/lib/activity";
import ActivityTrail from "@/components/ActivityTrail";
import Markdown from "@/components/Markdown";
import { AssistantInfo } from "@/lib/assistant";
import { UI } from "@/lib/strings";

export type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  error?: string;
  activity?: ActivityItem[];
  elapsedMs?: number;
};

export default function Chat({
  messages,
  busy,
  assistant,
  corpusEmpty,
  onSend,
  onCitationClick,
}: {
  messages: Message[];
  busy: boolean;
  assistant: AssistantInfo;
  corpusEmpty: boolean;
  onSend: (text: string) => void;
  onCitationClick: (citation: Citation) => void;
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    onSend(text);
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="mt-10 space-y-3 text-sm text-[var(--verifera-ink-muted)]">
            <p className="font-medium text-[#2b2540]">{assistant.description}</p>
            {assistant.suggestions.map((s) => (
              <button
                key={s}
                onClick={() => onSend(s)}
                className="block w-full rounded-lg border border-[var(--verifera-line)] bg-white p-2 text-left transition-colors hover:border-[var(--verifera-teal)] hover:bg-[var(--verifera-teal-soft)]"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((message, i) => (
          <MessageBubble key={i} message={message} onCitationClick={onCitationClick} />
        ))}
      </div>
      {corpusEmpty && (
        <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          <span className="font-medium">{UI.emptyCorpusTitle}</span> {UI.emptyCorpusHint}
        </div>
      )}
      <form onSubmit={submit} className="border-t border-[var(--verifera-line)] bg-white p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={assistant.placeholder}
            className="flex-1 rounded-lg border border-[var(--verifera-line)] px-3 py-2 text-sm outline-none transition-colors focus:border-[var(--verifera-teal)] focus:ring-2 focus:ring-[rgba(8,198,164,0.16)]"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-[var(--verifera-purple)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#2d1188] disabled:opacity-40 disabled:hover:bg-[var(--verifera-purple)]"
          >
            {UI.send}
          </button>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({
  message,
  onCitationClick,
}: {
  message: Message;
  onCitationClick: (citation: Citation) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="ml-8 rounded-xl rounded-br-sm bg-[var(--verifera-purple)] p-3 text-sm text-white">
        {message.content}
      </div>
    );
  }
  return (
    <div className="mr-4 rounded-xl rounded-bl-sm border border-[var(--verifera-line)] bg-white p-3 text-sm shadow-sm shadow-[#3a18a6]/[0.03]">
      {(message.streaming || !!message.activity?.length) && (
        <ActivityTrail
          activity={message.activity ?? []}
          streaming={!!message.streaming && !message.content}
          elapsedMs={message.elapsedMs}
        />
      )}
      <div className={`text-sm ${message.streaming && message.content ? "streaming-cursor" : ""}`}>
        <Markdown
          text={message.content}
          citations={message.citations}
          onCitationClick={onCitationClick}
        />
      </div>
      {message.error && (
        <div className="mt-2 rounded bg-red-50 p-2 text-xs text-red-700">
          {UI.errorPrefix} {message.error}
        </div>
      )}
      {!!message.citations?.length && (
        <SourceList citations={message.citations} onCitationClick={onCitationClick} />
      )}
    </div>
  );
}

/** The reference section: one entry per cited passage, numbered to match the
 *  markers in the prose. It is the only place the verbatim quote and the
 *  verification result are visible without hovering, which is the product. */
function SourceList({
  citations,
  onCitationClick,
}: {
  citations: Citation[];
  onCitationClick: (citation: Citation) => void;
}) {
  return (
    <div className="mt-3 space-y-1.5 border-t border-[var(--verifera-line)] pt-2">
      <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--verifera-ink-muted)]">
        {UI.sources}
      </div>
      {groupByMarker(citations).map((group) => {
        const first = group[0];
        return (
          <button
            key={first.chunk_id + first.marker}
            onClick={() => onCitationClick(first)}
            className="flex w-full gap-2 rounded px-1 py-0.5 text-left transition-colors hover:bg-[var(--verifera-purple-soft)]"
          >
            <span className="w-4 shrink-0 pt-px text-right text-[11px] font-medium text-neutral-400">
              {first.marker ?? "·"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-1 text-xs text-neutral-700">
                <span className="truncate">{first.title ?? first.doc_id}</span>
                {first.page != null && (
                  <span className="shrink-0 text-neutral-400">p.{first.page}</span>
                )}
                <span className={first.verified ? "text-[var(--verifera-teal)]" : "text-amber-600"}>
                  {first.verified ? "✓" : "⚠"}
                </span>
              </span>
              {group.map((citation) => (
                <span
                  key={citation.quote}
                  className="mt-0.5 block text-[11px] italic leading-snug text-neutral-500"
                >
                  “{citation.quote}”
                </span>
              ))}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Two quotes from one chunk are one place in the document, so they share a
 *  number and a row. Citations arrive ordered by marker, so grouping runs of
 *  equal markers is enough; the un-cited ones at the end each keep their own. */
function groupByMarker(citations: Citation[]): Citation[][] {
  const groups: Citation[][] = [];
  for (const citation of citations) {
    const last = groups[groups.length - 1];
    if (last && citation.marker != null && last[0].marker === citation.marker) last.push(citation);
    else groups.push([citation]);
  }
  return groups;
}
