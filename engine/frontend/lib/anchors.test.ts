import { describe, expect, it } from "vitest";
import { buildIndex, findAnchor, locateCitation, normalizeNeedle } from "./anchors";

describe("normalizeNeedle", () => {
  it("unifies typography, case and whitespace like the backend", () => {
    expect(normalizeNeedle("“COLOR  ULTIME” – 10’")).toBe("\"color ultime\" - 10'");
  });

  it("compact form drops punctuation and spacing", () => {
    expect(normalizeNeedle("Tempo di posa: 30-45 minuti!", true)).toBe(
      "tempodiposa3045minuti",
    );
  });
});

describe("findAnchor", () => {
  it("finds a needle spanning multiple blocks and maps back to source offsets", () => {
    // three DOM text nodes; the passage crosses the node boundary
    const blocks = ["La crema va ", "miscelata 1:1 con IGORA", " ROYAL Oil Developer."];
    const index = buildIndex(blocks);
    const match = findAnchor(index, normalizeNeedle("miscelata 1:1 con IGORA ROYAL"));
    expect(match).not.toBeNull();
    expect(match!.start).toEqual({ block: 1, offset: 0 });
    expect(match!.end.block).toBe(2);
    expect(blocks[2].slice(0, match!.end.offset)).toBe(" ROYAL");
  });

  it("returns null when absent", () => {
    const index = buildIndex(["testo qualunque"]);
    expect(findAnchor(index, normalizeNeedle("assente"))).toBeNull();
  });
});

describe("locateCitation", () => {
  it("matches the quote despite typographic and spacing differences", () => {
    const blocks = ["Schiarisce  fino a\n6 toni – senza ammoniaca."];
    const match = locateCitation(blocks, "schiarisce fino a 6 toni — senza ammoniaca", "");
    expect(match).not.toBeNull();
    expect(match!.start).toEqual({ block: 0, offset: 0 });
  });

  it("falls back to compact matching when punctuation diverges", () => {
    const blocks = ["Tempo di posa 30/45 minuti"];
    const match = locateCitation(blocks, "Tempo di posa: 30-45 minuti.", "");
    expect(match).not.toBeNull();
  });

  it("falls back to a chunk_text prefix when the quote is missing", () => {
    const blocks = ["Il prodotto va applicato su capelli asciutti e lavato dopo la posa."];
    const match = locateCitation(
      blocks,
      "frase inventata dal modello",
      "Il prodotto va applicato su capelli asciutti" + " x".repeat(200),
    );
    expect(match).not.toBeNull();
    expect(match!.start.offset).toBe(0);
  });
});
