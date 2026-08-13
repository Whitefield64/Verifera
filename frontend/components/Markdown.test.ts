import { describe, expect, it } from "vitest";
import { linkify } from "@/components/Markdown";

/** Mirrors the pattern in Markdown.tsx. */
const HTML_LINE_BREAK = /<br\s*\/?>/gi;
const clean = (text: string) => text.replace(HTML_LINE_BREAK, " ");

describe("html line breaks in model output", () => {
  it("removes the tags models put inside table cells", () => {
    const cell = "| Area | (a) systems<br>(b) others<br/>(c) more |";
    expect(clean(cell)).toBe("| Area | (a) systems (b) others (c) more |");
  });

  it("handles spacing and casing variants", () => {
    expect(clean("a<BR>b<br />c<br/>d")).toBe("a b c d");
  });

  it("also strips inside a code span, which is the accepted cost", () => {
    // Answers over a document corpus discuss law, not HTML. Worth revisiting
    // for a pack whose documents are about markup.
    expect(clean("Use `<br>` for a break")).toBe("Use ` ` for a break");
  });

  it("leaves stray angle brackets alone", () => {
    expect(clean("3 < 4 > 2 and a<b")).toBe("3 < 4 > 2 and a<b");
  });
});

describe("citation markers", () => {
  it("turns every marker into a link the renderer can intercept", () => {
    expect(linkify("Applies from 2025 [[1]]. And from 2026 [[2]].")).toBe(
      "Applies from 2025 [1](#cite-1). And from 2026 [2](#cite-2).",
    );
  });

  it("repeats the same link for a source cited twice", () => {
    expect(linkify("One [[1]] two [[2]] one again [[1]]")).toBe(
      "One [1](#cite-1) two [2](#cite-2) one again [1](#cite-1)",
    );
  });

  it("leaves bracketed prose that is not a marker alone", () => {
    expect(linkify("Annex [[III]] and a range [[1-2]]")).toBe("Annex [[III]] and a range [[1-2]]");
  });

  it("does not touch a chunk id the backend failed to strip", () => {
    // Numbering claims every reference that resolved; anything still carrying a
    // digest here is a reference to a source that did not survive verification.
    const leftover = "Claim [[ai-act-en#0f3c1a2b4d5e6f70]]";
    expect(linkify(leftover)).toBe(leftover);
  });
});
