/**
 * The copy around the answer, served by the backend from config/assistant.yaml.
 *
 * The fallback is deliberately generic: if the API is unreachable the UI shows
 * neutral chrome rather than a second, drifting copy of the wording.
 */
import { API_URL } from "@/lib/api";

export type AssistantInfo = {
  name: string;
  title: string;
  description: string;
  locale: string;
  heading: string;
  tagline: string;
  placeholder: string;
  suggestions: string[];
};

export const FALLBACK_ASSISTANT: AssistantInfo = {
  name: "Verifera",
  title: "Verifera",
  description: "",
  locale: "en",
  heading: "Verifera",
  tagline: "A verifiable document agent for your knowledge base.",
  placeholder: "Ask a question...",
  suggestions: [],
};

export async function fetchAssistant(): Promise<AssistantInfo> {
  try {
    const res = await fetch(`${API_URL}/api/assistant`);
    if (!res.ok) return FALLBACK_ASSISTANT;
    return { ...FALLBACK_ASSISTANT, ...(await res.json()) };
  } catch {
    return FALLBACK_ASSISTANT;
  }
}
