import { useState } from "react";
import { Check, Pencil, RotateCcw, X } from "lucide-react";
import type { Claim } from "../types";
import { CitationChips } from "./Evidence";
import { Badge, ClaimStateBadge, LabelBadge, TYPE_TONE } from "./ui";

export function ClaimCard({ c, onOpen, onReview, compact }: {
  c: Claim; onOpen: (c: Claim) => void; onReview?: (c: Claim, decision: string, value?: string) => Promise<void>; compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(c.value);
  const [busy, setBusy] = useState(false);
  const act = async (d: string, v?: string) => {
    if (!onReview) return;
    setBusy(true);
    try { await onReview(c, d, v); setEditing(false); } finally { setBusy(false); }
  };
  const ev = c.evidence[0];
  return (
    <div className="claim fade" style={c.review_status === "rejected" ? { opacity: 0.55 } : undefined}>
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div className="flex1">
          <div className="claim-meta">
            <Badge tone={TYPE_TONE[c.ctype]}>{c.ctype}</Badge>
            <ClaimStateBadge c={c} />
            {c.modality === "proposal" && <Badge tone="amber">Proposal</Badge>}
            {c.modality === "tacit" && <Badge tone="pink">Tacit</Badge>}
            {c.origin === "testimony" && c.review_status !== "pending" && <Badge tone="pink">From testimony</Badge>}
            {c.origin === "llm" && <Badge tone="accent">AI-proposed</Badge>}
            {c.labels.map((l) => <LabelBadge key={l} label={l} />)}
          </div>
          <div className="claim-statement mt-s">{c.statement}</div>
          {c.original_value && <div className="tiny muted">was “{c.original_value}”</div>}
        </div>
        {onReview && (
          <div className="row" style={{ gap: 6 }}>
            {c.review_status === "pending" && !c.conflict_group ? (
              <>
                <button className="btn sm success" disabled={busy} onClick={() => act("accept")} title="Accept"><Check size={13} /> Accept</button>
                <button className="btn sm" disabled={busy} onClick={() => setEditing((x) => !x)} title="Edit"><Pencil size={13} /></button>
                <button className="btn sm danger" disabled={busy} onClick={() => act("reject")} title="Reject"><X size={13} /></button>
              </>
            ) : c.review_status !== "pending" ? (
              <button className="btn sm ghost" disabled={busy} onClick={() => act("reset")} title="Undo review"><RotateCcw size={13} /> Undo</button>
            ) : null}
          </div>
        )}
      </div>
      {editing && (
        <div className="row">
          <input className="input" value={val} onChange={(e) => setVal(e.target.value)} />
          <button className="btn sm primary" disabled={busy || !val.trim()} onClick={() => act("edit", val)}>Save & recheck</button>
        </div>
      )}
      {!compact && ev && <div className={`quote ${c.conflict_group ? "conflict" : ""}`}>{ev.quote}</div>}
      <div className="spread">
        <CitationChips claim={c} onOpen={() => onOpen(c)} />
        {c.review_note && <span className="tiny muted ellipsis" style={{ maxWidth: 320 }} title={c.review_note}>{c.review_note}</span>}
      </div>
    </div>
  );
}
