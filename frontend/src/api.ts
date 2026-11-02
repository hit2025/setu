import type { Case, Claim, Evidence, HandoverView, Job, Ledger, Question, Snapshot, Source, User, Gate, SystemInfo } from "./types";

const TOKEN_KEY = "setu.token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function req<T>(method: string, path: string, body?: any, isForm = false): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("setu:logout"));
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

const q = (o: Record<string, any>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && p.set(k, String(v)));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  personas: () => req<User[]>("GET", "/api/auth/personas"),
  login: (user_id: string) => req<{ token: string; user: User }>("POST", "/api/auth/login", { user_id }),
  me: () => req<User>("GET", "/api/auth/me"),
  system: () => req<SystemInfo>("GET", "/api/system"),

  cases: () => req<Case[]>("GET", "/api/cases"),
  case: (id: string) => req<Case>("GET", `/api/cases/${id}`),
  createCase: (b: any) => req<Case>("POST", "/api/cases", b),
  createDemo: () => req<Case>("POST", "/api/cases/demo"),
  deleteCase: (id: string) => req("DELETE", `/api/cases/${id}`),

  sources: (id: string) => req<Source[]>("GET", `/api/cases/${id}/sources`),
  source: (sid: string) => req<Source>("GET", `/api/sources/${sid}`),
  upload: (id: string, files: File[], labels: Record<string, string>) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("labels", JSON.stringify(labels));
    return req<{ added: Source[]; notes: string[] }>("POST", `/api/cases/${id}/sources`, fd, true);
  },
  relabel: (sid: string, label: string) => req<Source>("PATCH", `/api/sources/${sid}`, { label }),
  deleteSource: (sid: string) => req("DELETE", `/api/sources/${sid}`),

  reconstruct: (id: string) => req<{ id: string; status: string }>("POST", `/api/cases/${id}/reconstruct`),
  job: (jid: string) => req<Job>("GET", `/api/jobs/${jid}`),

  ledger: (id: string) => req<Ledger>("GET", `/api/cases/${id}/ledger`),
  review: (cid: string, decision: string, value?: string, note?: string) =>
    req<{ claim: Claim }>("POST", `/api/claims/${cid}/review`, { decision, value, note }),
  bulkAccept: (id: string) => req<{ accepted: number }>("POST", `/api/cases/${id}/claims/bulk-accept`),
  manualClaim: (id: string, b: any) => req("POST", `/api/cases/${id}/claims`, b),

  questions: (id: string) => req<Question[]>("GET", `/api/cases/${id}/questions`),
  answer: (qid: string, value: string, answer: string) => req("POST", `/api/questions/${qid}/answer`, { value, answer }),

  gate: (id: string) => req<Gate>("GET", `/api/cases/${id}/gate`),
  approve: (id: string, note: string) => req<{ version: number; hash: string }>("POST", `/api/cases/${id}/snapshots`, { note }),
  snapshots: (id: string) => req<Snapshot[]>("GET", `/api/cases/${id}/snapshots`),
  audit: (id: string) => req<any[]>("GET", `/api/cases/${id}/audit`),

  handover: (id: string, version?: number, as_role?: string) => req<HandoverView>("GET", `/api/cases/${id}/handover${q({ version, as_role })}`),
  citation: (id: string, claim_id: string, evidence_id: string, version?: number, as_role?: string) =>
    req<any>("GET", `/api/cases/${id}/handover/citation${q({ claim_id, evidence_id, version, as_role })}`),
  search: (id: string, text: string, version?: number, as_role?: string) =>
    req<{ score: number; claim: Claim }[]>("GET", `/api/cases/${id}/handover/search${q({ q: text, version, as_role })}`),
  ack: (id: string, version: number) => req<{ at: string; view_hash: string }>("POST", `/api/cases/${id}/handover/ack`, { version }),
};

export type { Evidence };
