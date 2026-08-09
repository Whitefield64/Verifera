export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type BBox = {
  x: number;
  y: number;
  w: number;
  h: number;
  page_w: number;
  page_h: number;
  page?: number;
};

export type Citation = {
  doc_id: string;
  chunk_id: string;
  page: number | null;
  bbox: BBox | null;
  bboxes: BBox[] | null;
  quote: string;
  chunk_text: string;
  verified: boolean;
};

export type ChatResponse = {
  answer: string;
  citations: Citation[];
  path: "rag" | "agent";
  meta: Record<string, unknown>;
};

export type DocInfo = {
  doc_id: string;
  format: "pdf" | "html" | "docx";
  status: string;
  page_count: number | null;
  chunk_count: number | null;
  table_count: number | null;
  error: string | null;
};

export type HistoryTurn = { role: "user" | "assistant"; content: string };

/** One step of the agent path, already shaped for rendering. */
export type ToolEvent = {
  name: string;
  title: string;
  summary: string;
  items: string[];
};

export function docFileUrl(docId: string): string {
  return `${API_URL}/api/documents/${encodeURIComponent(docId)}/file`;
}

/** Estrazione testuale (Docling, già in workspace): fallback quando l'originale
 *  non è renderizzabile senza eseguire script lato client (vedi HtmlViewer). */
export function docTextUrl(docId: string): string {
  return `${API_URL}/api/documents/${encodeURIComponent(docId)}/text`;
}

export async function fetchDocuments(): Promise<DocInfo[]> {
  const res = await fetch(`${API_URL}/api/documents`);
  if (!res.ok) throw new Error(`GET /api/documents → ${res.status}`);
  return res.json();
}

/** POST /api/chat/stream and dispatch SSE events until the stream closes. */
export async function streamChat(
  message: string,
  history: HistoryTurn[],
  handlers: {
    onDelta: (text: string) => void;
    onDone: (response: ChatResponse) => void;
    onThinking?: (text: string) => void;
    onTool?: (tool: ToolEvent) => void;
  },
): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok || !res.body) throw new Error(`chat/stream → ${res.status}`);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const data = frame.match(/^data: (.+)$/m)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") handlers.onDone(payload);
      else if (event === "thinking") handlers.onThinking?.(payload.text);
      else if (event === "tool") handlers.onTool?.(payload);
      else if (event === "error") throw new Error(payload.detail);
    }
  }
}
