"use client";

import { ActivityItem, groupActivity, statusLabel, traySummary } from "@/lib/activity";
import { UI } from "@/lib/strings";

/** Trail del percorso agentico: righe espandibili durante l'elaborazione,
 *  riga-sommario riapribile a risposta completata. Per il path RAG mostra
 *  solo la riga di stato finché non arriva il primo token. */
export default function ActivityTrail({
  activity,
  streaming,
  elapsedMs,
}: {
  activity: ActivityItem[];
  streaming: boolean;
  elapsedMs?: number;
}) {
  if (streaming) {
    return (
      <div className="space-y-1">
        <TrailRows activity={activity} />
        <div className="flex items-center gap-2 py-0.5 text-xs text-neutral-500">
          <span className="h-3 w-3 shrink-0 animate-spin rounded-full border border-neutral-300 border-t-amber-500" />
          {statusLabel(activity)}
        </div>
      </div>
    );
  }
  if (activity.length === 0) return null;
  return (
    <details className="group mb-2 rounded-lg border border-neutral-100 bg-neutral-50 px-2 py-1">
      <summary className="cursor-pointer select-none list-none text-xs text-neutral-500 hover:text-neutral-700">
        <Chevron /> {traySummary(activity, elapsedMs)}
      </summary>
      <div className="mt-1 border-t border-neutral-100 pt-1">
        <TrailRows activity={activity} />
      </div>
    </details>
  );
}

function TrailRows({ activity }: { activity: ActivityItem[] }) {
  if (activity.length === 0) return null;
  return (
    <div className="space-y-0.5 text-xs">
      {groupActivity(activity).map((group, i) =>
        group.type === "thinking" ? (
          <details key={i} className="group/row rounded px-1 hover:bg-neutral-100">
            <summary className="cursor-pointer select-none list-none py-0.5 text-neutral-500">
              <Chevron row /> <span className="text-neutral-400">∴</span> {UI.reasoning}
            </summary>
            <div className="mb-1 ml-4 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-white p-2 leading-relaxed text-neutral-500">
              {group.texts.join("\n\n")}
            </div>
          </details>
        ) : (
          <details key={i} className="group/row rounded px-1 hover:bg-neutral-100">
            <summary className="cursor-pointer select-none list-none py-0.5 text-neutral-500">
              <Chevron row /> <span className="text-neutral-400">⚙</span>{" "}
              <span className="font-medium">{group.tool.name}</span>
              {group.tool.title && <span className="text-neutral-400"> · {group.tool.title}</span>}
            </summary>
            <div className="mb-1 ml-4 rounded bg-white p-2 text-neutral-500">
              <div>→ {group.tool.summary}</div>
              {group.tool.items.length > 0 && (
                <ul className="mt-0.5 space-y-0.5">
                  {group.tool.items.map((item, j) => (
                    <li key={j} className="truncate pl-3">
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </details>
        ),
      )}
    </div>
  );
}

function Chevron({ row }: { row?: boolean }) {
  return (
    <span
      className={`inline-block w-3 text-[9px] text-neutral-400 transition-transform ${
        row ? "group-open/row:rotate-90" : "group-open:rotate-90"
      }`}
    >
      ▶
    </span>
  );
}
