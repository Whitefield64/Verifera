import { describe, expect, it } from "vitest";

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
