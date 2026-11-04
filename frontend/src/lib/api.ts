/**
 * Market Intelligence Lab — Centralized API Client & Ngrok Header Helpers
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const API_HEADERS: Record<string, string> = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

/**
 * Standard fetch wrapper that automatically applies Ngrok bypass headers and Content-Type.
 */
export async function apiFetch(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  return fetch(url, {
    ...options,
    headers: {
      ...API_HEADERS,
      ...(options.headers || {}),
    },
  });
}
