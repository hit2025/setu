export type Role = "reviewer" | "departing" | "engineer" | "coordinator";

export interface User { id: string; name: string; role: Role; title: string }

export interface SystemInfo {
  extractor: { mode: string; label: string; model: string | null };
  labels: { label: string; title: string; desc: string; readers: string[] }[];
  today: string;
}

export interface Case {
  id: string; name: string; project: string; description: string; status: string; departure_date: string;
  recipient_roles: string[]; departing: { id: string; name: string } | null; reviewer: { id: string; name: string } | null;
  created_at: string; extractor_used: string; stage: number;
  counts: Partial<{ sources: number; claims: number; pending: number; accepted: number; rejected: number; conflicts: number;
    open_questions: number; versions: number; receipts: number }>;
  latest_version: number | null; acknowledged: boolean;
  job?: { id: string; status: string; progress: number; message: string } | null;
}

export interface Source {
  id: string; filename: string; kind: string; label: string; raw_hash: string; content_hash: string; char_count: number;
  masked: Record<string, number>; authored_at: string; uploaded_by: string; uploaded_at: string; extracted: boolean;
  excluded_reason: string; content?: string; passages?: { id: string; start: number; end: number; context: string }[];
}

export interface Evidence {
  id: string; source_id: string; source_name: string; source_label: string; passage_id: string; start: number; end: number;
  quote: string; source_hash: string; valid: boolean;
}

export interface Claim {
  id: string; ctype: string; subject: string; attribute: string; value: string; statement: string; modality: string;
  occurred_at: string; origin: string; support: string; anchored: boolean; conflict_group: string | null;
  review_status: string; review_note: string; original_value: string; reviewed_by: string; reviewed_at: string | null;
  allowed_roles?: string[]; labels: string[]; confidence: number; task_id: string | null; question_id: string | null;
  evidence: Evidence[];
}

export interface Check { check: string; ok: boolean; detail: string }
export interface Prereq { label: string; kind: string; ref: string; ok: boolean; detail: string; claim_id: string }
export interface Action {
  key: string; title: string; status: string; owner: string | null; due: string | null; readiness: string; rank: number;
  checks: Check[]; prerequisites: Prereq[]; blockers: string[]; risk_ids: string[]; claim_ids: string[]; labels: string[]; mine?: boolean;
}

export interface Conflict { group: string; state: string; winner: string | null; claim_ids: string[]; attribute: string }
export interface TimelineEvent { date: string; kind: string; text: string; claim_id: string; conflict: boolean }

export interface Ledger {
  claims: Claim[]; conflicts: Conflict[]; actions: Action[];
  transfers: { area: string; owner: string; claim_id: string }[]; timeline: TimelineEvent[];
}

export interface Question {
  id: string; kind: string; prompt: string; target: string; subject: string; attribute: string; options: string[];
  related_claims: string[]; label: string; status: string; answer: string; answer_value: string; answered_by: string;
  answered_at: string | null;
}

export interface Job { id: string; status: string; progress: number; message: string; result: any }

export interface Gate {
  ok: boolean; issues: { code: string; message: string; ids: string[] }[];
  counts: { total: number; pending: number; accepted: number; edited: number; rejected: number; unresolved: number; open_conflicts: number };
}

export interface Snapshot {
  id: string; version: number; hash: string; approved_by: string; approved_at: string; note: string; claims: number;
  actions: number; diff: { added: number; removed: number } | null;
  receipts: { user_id: string; role: string; at: string; view_hash: string }[];
}

export interface HandoverView {
  version: number; snapshot_id: string; snapshot_hash: string; role: string; view_hash: string; latest_version: number;
  versions: number[]; preview: boolean; receipt: { at: string; view_hash: string } | null;
  case: { id: string; name: string; project: string; departing: string; departure_date: string; description: string };
  approved_by: string; approved_at: string; note: string;
  first_action: Action | null; actions: Action[]; transfers: { area: string; owner: string; claim_id: string }[];
  decisions: Claim[]; proposals: Claim[]; owners: Claim[]; risks: Claim[]; contacts: Claim[];
  unresolved: { group: string; attribute: string; claims: Claim[] }[]; claims: Claim[]; timeline: TimelineEvent[];
  open_questions: { id: string; kind: string; prompt: string }[];
  sources: { id: string; filename: string; label: string; content_hash: string; kind: string }[];
  stats: { claims: number; actions: number; ready: number; blocked: number; unresolved: number };
}
