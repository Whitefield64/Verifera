/**
 * Text-anchor matching for documents without page geometry (HTML/DOCX).
 *
 * Mirrors the backend normalization (backend/app/citations.py): NFKC, typographic
 * chars unified, lowercase, whitespace collapsed. The index maps every normalized
 * character back to (block, offset) in the source blocks — for the DOM, blocks are
 * text nodes — so a match can be turned into a precise Range.
 */

const CHAR_MAP: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "“": '"',
  "”": '"',
  "–": "-",
  "—": "-",
  " ": " ",
};

export type SourcePos = { block: number; offset: number };
export type AnchorIndex = { norm: string; map: SourcePos[] };
/** Match range over source blocks; end is exclusive. */
export type AnchorMatch = { start: SourcePos; end: SourcePos };

function normalizeChar(char: string): string {
  const mapped = CHAR_MAP[char] ?? char;
  return mapped.normalize("NFKC").toLowerCase();
}

/**
 * Build a searchable normalized stream over source blocks.
 * `compact` drops everything but letters/digits: punctuation- and
 * spacing-insensitive matching, same idea as the backend quote verifier.
 */
export function buildIndex(blocks: string[], compact = false): AnchorIndex {
  const norm: string[] = [];
  const map: SourcePos[] = [];
  for (let block = 0; block < blocks.length; block++) {
    const text = blocks[block];
    for (let offset = 0; offset < text.length; offset++) {
      for (const char of normalizeChar(text[offset])) {
        if (/\s/.test(char)) {
          if (!compact && norm.length > 0 && norm[norm.length - 1] !== " ") {
            norm.push(" ");
            map.push({ block, offset });
          }
        } else if (!compact || /[\p{L}\p{N}]/u.test(char)) {
          norm.push(char);
          map.push({ block, offset });
        }
      }
    }
    // block boundaries count as whitespace: DOM text nodes rarely butt words together
    if (!compact && norm.length > 0 && norm[norm.length - 1] !== " ") {
      norm.push(" ");
      map.push({ block, offset: Math.max(0, text.length - 1) });
    }
  }
  return { norm: norm.join(""), map };
}

export function normalizeNeedle(text: string, compact = false): string {
  return buildIndex([text], compact).norm.trim();
}

function matchAt(index: AnchorIndex, from: number, length: number): AnchorMatch {
  const startPos = index.map[from];
  const lastPos = index.map[from + length - 1];
  return { start: startPos, end: { block: lastPos.block, offset: lastPos.offset + 1 } };
}

export function findAnchor(index: AnchorIndex, needle: string): AnchorMatch | null {
  if (!needle) return null;
  const at = index.norm.indexOf(needle);
  if (at === -1) return null;
  return matchAt(index, at, needle.length);
}

/** Longest prefix of the needle present in the index (binary search — prefix
 *  presence is monotonic), if at least `minLength` chars of it match. */
function findLongestPrefixAnchor(
  index: AnchorIndex,
  needle: string,
  minLength: number,
): AnchorMatch | null {
  if (needle.length < minLength) return null;
  let ok = 0;
  let low = minLength;
  let high = needle.length;
  while (low <= high) {
    const mid = Math.ceil((low + high) / 2);
    if (index.norm.includes(needle.slice(0, mid))) {
      ok = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  if (ok === 0) return null;
  return matchAt(index, index.norm.indexOf(needle.slice(0, ok)), ok);
}

/**
 * Locate the best anchor for a citation inside source blocks: the exact quote,
 * else the exact chunk text, else the longest matching prefix of the chunk text
 * (rendered docs can diverge from extracted text past the chunk start); each
 * first in whitespace-collapsed form, then punctuation-insensitive (compact).
 */
export function locateCitation(
  blocks: string[],
  quote: string,
  chunkText: string,
): AnchorMatch | null {
  for (const isCompact of [false, true]) {
    const index = buildIndex(blocks, isCompact);
    const quoteNeedle = normalizeNeedle(quote, isCompact);
    const chunkNeedle = normalizeNeedle(chunkText, isCompact);
    const match =
      findAnchor(index, quoteNeedle) ??
      findAnchor(index, chunkNeedle) ??
      findLongestPrefixAnchor(index, chunkNeedle, isCompact ? 20 : 25);
    if (match) return match;
  }
  return null;
}
