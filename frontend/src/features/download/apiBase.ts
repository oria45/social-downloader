export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export function previewSrc(url: string): string {
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}
