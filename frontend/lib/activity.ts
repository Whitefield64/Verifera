import { ToolEvent } from "@/lib/api";
import { UI } from "@/lib/strings";

/** Attività del percorso agentico accumulate durante lo streaming. */
export type ActivityItem =
  | { type: "thinking"; text: string }
  | ({ type: "tool" } & ToolEvent);

export type ActivityGroup = { type: "thinking"; texts: string[] } | { type: "tool"; tool: ToolEvent };

/** Raggruppa i "thinking" consecutivi in un unico blocco collassabile, senza
 *  alterare l'ordine cronologico: il ragionamento resta intrecciato con i tool
 *  esattamente come è arrivato (l'agente pensa, agisce, pensa ancora…). */
export function groupActivity(activity: ActivityItem[]): ActivityGroup[] {
  const groups: ActivityGroup[] = [];
  for (const item of activity) {
    if (item.type === "thinking") {
      const last = groups[groups.length - 1];
      if (last?.type === "thinking") last.texts.push(item.text);
      else groups.push({ type: "thinking", texts: [item.text] });
    } else {
      groups.push({
        type: "tool",
        tool: { name: item.name, title: item.title, summary: item.summary, items: item.items },
      });
    }
  }
  return groups;
}

/** Understated status line, derived from the most recent activity. */
export function statusLabel(activity: ActivityItem[]): string {
  const last = activity[activity.length - 1];
  if (!last) return UI.searching;
  if (last.type === "thinking") return UI.thinking;
  switch (last.name) {
    case "semantic_search":
      return UI.searching;
    case "read_document_section":
      return UI.reading(last.title.split(" · ")[0]);
    case "get_document_metadata":
      return UI.readingIndex(last.title);
    default:
      return UI.composing;
  }
}

/** Summary for the collapsed row once the answer is complete. */
export function traySummary(activity: ActivityItem[], elapsedMs?: number): string {
  const tools = activity.filter((a) => a.type === "tool").length;
  const parts: string[] = [UI.deepPath];
  if (tools > 0) parts.push(`${tools} ${tools === 1 ? UI.step : UI.steps}`);
  if (elapsedMs != null) parts.push(`${Math.round(elapsedMs / 1000)}s`);
  return parts.join(" · ");
}
