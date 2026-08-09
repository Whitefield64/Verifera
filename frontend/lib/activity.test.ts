import { describe, expect, it } from "vitest";
import { ActivityItem, groupActivity, statusLabel, traySummary } from "./activity";
import { UI } from "./strings";

const search: ActivityItem = {
  type: "tool",
  name: "semantic_search",
  title: "«annex III»",
  summary: "8 results",
  items: [],
};
const read: ActivityItem = {
  type: "tool",
  name: "read_document_section",
  title: "reg-2024-1689 · sections/03-prohibited-practices.md",
  summary: "4200 characters read",
  items: [],
};
const think = (text: string): ActivityItem => ({ type: "thinking", text });

describe("statusLabel", () => {
  it("starts from search when nothing has happened yet", () => {
    expect(statusLabel([])).toBe(UI.searching);
  });
  it("follows the most recent activity", () => {
    expect(statusLabel([search])).toBe(UI.searching);
    expect(statusLabel([search, read])).toBe(UI.reading("reg-2024-1689"));
    expect(statusLabel([search, think("...")])).toBe(UI.thinking);
  });
});

describe("traySummary", () => {
  it("counts tools only and formats the seconds", () => {
    expect(traySummary([search, think("..."), read], 31400)).toBe(
      `${UI.deepPath} · 2 ${UI.steps} · 31s`,
    );
    expect(traySummary([search], undefined)).toBe(`${UI.deepPath} · 1 ${UI.step}`);
  });
});

describe("groupActivity", () => {
  it("keeps chronological order instead of hoisting all thinking to the top", () => {
    // exactly the reported scenario: thought, searches, thought, reads, thought
    const activity = [think("first"), search, search, think("second"), read, think("third")];
    const groups = groupActivity(activity);
    expect(groups.map((g) => g.type)).toEqual([
      "thinking",
      "tool",
      "tool",
      "thinking",
      "tool",
      "thinking",
    ]);
  });

  it("merges consecutive thinking events into one block", () => {
    const groups = groupActivity([think("a"), think("b"), search, think("c")]);
    expect(groups).toHaveLength(3);
    expect(groups[0]).toEqual({ type: "thinking", texts: ["a", "b"] });
    expect(groups[2]).toEqual({ type: "thinking", texts: ["c"] });
  });

  it("does not alter the tool fields", () => {
    const groups = groupActivity([search]);
    expect(groups[0]).toEqual({
      type: "tool",
      tool: { name: search.name, title: search.title, summary: search.summary, items: search.items },
    });
  });
});
