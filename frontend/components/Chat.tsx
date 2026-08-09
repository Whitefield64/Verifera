"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Citation } from "@/lib/api";
import { ActivityItem } from "@/lib/activity";
import ActivityTrail from "@/components/ActivityTrail";
import Markdown from "@/components/Markdown";
import { PackInfo } from "@/lib/pack";
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
  pack,
  onSend,
  onCitationClick,
}: {
  messages: Message[];
  busy: boolean;
  pack: PackInfo;
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
          <div className="mt-10 space-y-3 text-sm text-neutral-500">
            <p className="font-medium text-neutral-700">{pack.description}</p>
            {pack.suggestions.map((s) => (
              <button
                key={s}
                onClick={() => onSend(s)}
                className="block w-full rounded-lg border border-neutral-200 bg-white p-2 text-left hover:border-amber-400 hover:bg-amber-50"
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
      <form onSubmit={submit} className="border-t border-neutral-200 p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={pack.placeholder}
            className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-amber-500"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
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
      <div className="ml-8 rounded-xl rounded-br-sm bg-neutral-900 p-3 text-sm text-white">
        {message.content}
      </div>
    );
  }
  return (
    <div className="mr-4 rounded-xl rounded-bl-sm border border-neutral-200 bg-white p-3 text-sm shadow-sm">
      {(message.streaming || !!message.activity?.length) && (
        <ActivityTrail
          activity={message.activity ?? []}
          streaming={!!message.streaming && !message.content}
          elapsedMs={message.elapsedMs}
        />
      )}
      <div className={`text-sm ${message.streaming && message.content ? "streaming-cursor" : ""}`}>
        <Markdown text={message.content} />
      </div>
      {message.error && (
        <div className="mt-2 rounded bg-red-50 p-2 text-xs text-red-700">
          {UI.errorPrefix} {message.error}
        </div>
      )}
      {!!message.citations?.length && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-neutral-100 pt-2">
          {message.citations.map((citation, i) => (
            <button
              key={`${citation.chunk_id}-${i}`}
              onClick={() => onCitationClick(citation)}
              title={citation.quote}
              className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                citation.verified
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-400"
                  : "border-amber-300 bg-amber-50 text-amber-800 hover:border-amber-500"
              }`}
            >
              [{i + 1}] {citation.doc_id}
              {citation.page != null && ` · p.${citation.page}`}
              {citation.verified ? " ✓" : " ⚠"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
