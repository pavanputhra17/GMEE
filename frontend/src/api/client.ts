// IPv4-explicit on purpose: on Windows `localhost` resolves to ::1 first, and a
// stale Docker port-proxy socket on [::1]:8000 would silently swallow every call
// (the SPA then drops into demo telemetry). Override with VITE_API_BASE_URL.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

const parseError = async (response: Response): Promise<string> => {
  const data = (await response.json().catch(() => ({}))) as { detail?: unknown };
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  // FastAPI validation errors arrive as an array of { msg, ... }
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return `HTTP Error ${response.status}`;
};

export const apiClient = {
  get: async (endpoint: string) => {
    const response = await fetch(`${BASE_URL}${endpoint}`);
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    return response.json();
  },
  post: async (endpoint: string, body: unknown) => {
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    return response.json();
  },
};
