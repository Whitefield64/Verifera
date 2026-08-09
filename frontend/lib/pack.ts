/**
 * Domain copy, served by the backend from the active domain pack.
 *
 * The fallback is deliberately generic: if the API is unreachable the UI shows
 * neutral chrome rather than a second, drifting copy of the domain wording.
 */
import { API_URL } from "@/lib/api";

export type PackInfo = {
  name: string;
  title: string;
  description: string;
  locale: string;
  heading: string;
  tagline: string;
  placeholder: string;
  suggestions: string[];
};

export const FALLBACK_PACK: PackInfo = {
  name: "unknown",
  title: "Document Assistant",
  description: "",
  locale: "en",
  heading: "Document Assistant",
  tagline: "",
  placeholder: "Ask a question…",
  suggestions: [],
};

export async function fetchPack(): Promise<PackInfo> {
  try {
    const res = await fetch(`${API_URL}/api/pack`);
    if (!res.ok) return FALLBACK_PACK;
    return { ...FALLBACK_PACK, ...(await res.json()) };
  } catch {
    return FALLBACK_PACK;
  }
}
