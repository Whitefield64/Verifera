/**
 * UI chrome copy. Domain wording does NOT belong here — it comes from the
 * domain pack over GET /api/pack (see lib/pack.ts), so retargeting the system
 * at another corpus needs no frontend change.
 */
export const UI = {
  send: "Send",
  errorPrefix: "Error:",
  sources: "Sources",
  viewerEmpty: [
    "Click a citation in the chat to open the original document",
    "with the passage highlighted.",
  ],
  pdfLoading: "Loading PDF…",
  pdfError: "Could not load the PDF.",
  docLoading: "Loading document…",
  passageNotFound: "Passage could not be located automatically in the document. Citation:",
  citedPassage: "Cited passage:",
  scriptsBlocked:
    "This page needs JavaScript to render its content: for safety we do not execute it. Showing the extracted text instead.",
  reasoning: "Reasoning",
  // activity trail
  searching: "Searching the documentation…",
  thinking: "Thinking…",
  readingIndex: (doc: string) => `Consulting the index of ${doc}…`,
  reading: (doc: string) => `Reading ${doc}…`,
  composing: "Composing the answer…",
  deepPath: "In-depth path",
  step: "step",
  steps: "steps",
} as const;
