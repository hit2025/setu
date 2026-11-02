import { AlertOctagon, CalendarClock, CheckCircle2, CircleSlash, FileText, ShieldAlert, User, XCircle } from "lucide-react";
import type { Action, Claim } from "../types";
import { Badge, READINESS, fmtDate } from "./ui";

export function ActionCard({ a, claims, onOpen }: { a: Action; claims: Map<string, Claim>; onOpen: (c: Claim) => void }) {
  const r = READINESS[a.readiness] || { label: a.readiness, tone: "" };
  const primary = a.claim_ids.map((id) => claims.get(id)).find((c) => c && c.ctype === "task") || claims.get(a.claim_ids[0]);
  const risks = a.risk_ids.map((id) => claims.get(id)).filter(Boolean) as Claim[];
  return (
    <div className={`action ${a.readiness} fade`}>
      <div className="rank">{a.rank}</div>
      <div className="flex1">
        <div className="row-wrap">
          <span className="strong" style={{ fontSize: 14.5 }}>{a.title}</span>
          <Badge tone={r.tone}>{r.label}</Badge>
          <Badge>{a.status.replace("_", " ")}</Badge>
          {a.mine && <Badge tone="accent">Assigned to you</Badge>}
        </div>
        <div className="row-wrap small muted mt-s" style={{ gap: 14 }}>
          <span className="row" style={{ gap: 5 }}><User size={13} /> {a.owner || <i>no owner</i>}</span>
          <span className="row" style={{ gap: 5 }}><CalendarClock size={13} /> {a.due ? fmtDate(a.due) : <i>no agreed date</i>}</span>
        </div>
        <div className="checks">
          {a.checks.map((c) => (
            <span key={c.check} className={`check ${c.ok ? "ok" : "bad"}`} title={c.detail}>
              {c.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />} {c.check}{!c.ok && `: ${c.detail.length > 46 ? c.detail.slice(0, 45) + "…" : c.detail}`}
            </span>
          ))}
        </div>
        {a.blockers.length > 0 && (
          <ul className="blockers">
            {a.blockers.map((b) => <li key={b}><AlertOctagon size={13} style={{ marginTop: 2, flexShrink: 0 }} /> {b}</li>)}
          </ul>
        )}
        {risks.length > 0 && (
          <div className="row-wrap mt-s">
            {risks.map((rk) => (
              <button key={rk.id} className="btn sm warn" onClick={() => onOpen(rk)} title={rk.value}>
                <ShieldAlert size={12} /> {rk.modality === "tacit" ? "Tacit workaround" : rk.ctype === "note" ? "Knowledge note" : "Linked risk"}: {rk.value.slice(0, 48)}{rk.value.length > 48 ? "…" : ""}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="col" style={{ alignItems: "flex-end" }}>
        {primary && <button className="btn sm" onClick={() => onOpen(primary)}><FileText size={13} /> Evidence</button>}
        {a.readiness === "done" && <span className="tiny muted row"><CircleSlash size={12} /> completed</span>}
      </div>
    </div>
  );
}
