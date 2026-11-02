import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, Clock, MessageSquareQuote, Send } from "lucide-react";
import { api } from "../api";
import { ClaimCard } from "../components/ClaimCard";
import { EvidenceDrawer } from "../components/Evidence";
import { Shell } from "../components/Shell";
import { Badge, Empty, LabelBadge, Spinner, Stat, fmtTime, useToast } from "../components/ui";
import type { Case, Claim, Ledger, Question } from "../types";

const PEOPLE = ["Meera Iyer", "Ananya Sen", "Dev Malhotra"];
const KIND: Record<string, string> = {
  conflict: "Sources disagree", missing_owner: "No owner", owner_leaving: "You own this", unknown_prereq: "Unknown prerequisite", tacit: "Only you know this",
};

export function Interview() {
  const { id = "" } = useParams();
  const [c, setC] = useState<Case | null>(null);
  const [qs, setQs] = useState<Question[]>([]);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [claim, setClaim] = useState<Claim | null>(null);
  const load = async () => {
    const [cc, q, l] = await Promise.all([api.case(id), api.questions(id), api.ledger(id)]);
    setC(cc); setQs(q); setLedger(l);
  };
  useEffect(() => { load(); }, [id]);
  const open = qs.filter((q) => q.status === "open");
  const answered = qs.filter((q) => q.status === "answered");
  const claims = useMemo(() => new Map((ledger?.claims ?? []).map((x) => [x.id, x])), [ledger]);
  if (!c) return <Shell crumbs={<b>Loading…</b>}><Spinner /></Shell>;

  return (
    <Shell crumbs={<><span>{c.project}</span><span>/</span><b>Handover interview</b></>}>
      <div className="hero-action">
        <div className="small muted">{c.project} · leaving {c.departure_date}</div>
        <h1 className="mt-s">Rohan, SETU needs {open.length} answer{open.length === 1 ? "" : "s"} from you.</h1>
        <p className="muted mt-s" style={{ maxWidth: 780 }}>
          Instead of a five-hour handover document, SETU reconstructed {ledger?.claims.length ?? 0} claims from the team's records and only asks what the evidence
          cannot settle. Your answers are stored as <b>labelled testimony</b> with their own hash and citation — the reviewer verifies them before anyone receives them.
        </p>
      </div>
      <div className="grid g3 mt">
        <Stat label="Open questions" value={open.length} tone={open.length ? "pink" : "teal"} />
        <Stat label="Answered (awaiting / after review)" value={answered.length} />
        <Stat label="Claims pre-filled from records" value={ledger?.claims.length ?? 0} />
      </div>
      <h2 className="mt-l mb">Questions</h2>
      {open.length === 0 ? <div className="card"><Empty icon={<CheckCircle2 size={32} color="var(--teal)" />} title="All questions answered — thank you.">The reviewer will verify your answers before release.</Empty></div> : (
        <div className="col">{open.map((q) => <QuestionForm key={q.id} q={q} claims={claims} onOpen={setClaim} onDone={load} />)}</div>
      )}
      {answered.length > 0 && (
        <>
          <h2 className="mt-l mb">Your answers</h2>
          <div className="col">
            {answered.map((q) => (
              <div key={q.id} className="claim">
                <div className="row-wrap"><Badge tone="teal"><CheckCircle2 size={11} /> Submitted</Badge><Badge tone="pink">Testimony · pending reviewer verification</Badge><span className="tiny muted">{fmtTime(q.answered_at)}</span></div>
                <div className="small muted">{q.prompt}</div>
                <div className="quote">{[q.answer_value, q.answer].filter(Boolean).join(" — ")}</div>
              </div>
            ))}
          </div>
        </>
      )}
      <h2 className="mt-l mb">Pre-filled claim ledger (read-only)</h2>
      <p className="small muted" style={{ marginTop: -8 }}>What SETU reconstructed from sources you are allowed to read. Spot something wrong? Say so in an answer — the reviewer decides.</p>
      <div className="col">{ledger?.claims.filter((x) => x.origin !== "testimony").slice(0, 60).map((x) => <ClaimCard key={x.id} c={x} onOpen={setClaim} compact />)}</div>
      <EvidenceDrawer claim={claim} mode={{ kind: "workspace" }} onClose={() => setClaim(null)} />
    </Shell>
  );
}

function QuestionForm({ q, claims, onOpen, onDone }: { q: Question; claims: Map<string, Claim>; onOpen: (c: Claim) => void; onDone: () => void }) {
  const needsValue = ["conflict", "missing_owner", "owner_leaving"].includes(q.kind);
  const options = q.kind === "conflict" ? q.options : needsValue ? PEOPLE : [];
  const [value, setValue] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const related = q.related_claims.map((id) => claims.get(id)).filter(Boolean) as Claim[];
  const submit = async () => {
    setBusy(true);
    try { await api.answer(q.id, value, text); toast("ok", "Saved as testimony. The reviewer will verify it before release."); onDone(); }
    catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  return (
    <div className="card card-pad fade">
      <div className="row-wrap"><Badge tone="pink">{KIND[q.kind] || q.kind}</Badge><LabelBadge label={q.label} /></div>
      <h3 className="mt-s" style={{ fontWeight: 600 }}>{q.prompt}</h3>
      {related.length > 0 && (
        <div className="row-wrap mt-s">
          <span className="tiny muted">Evidence:</span>
          {related.map((r) => <button key={r.id} className="btn sm ghost" style={{ border: "1px solid var(--border)" }} onClick={() => onOpen(r)}><MessageSquareQuote size={12} /> {r.evidence[0]?.source_name}: “{r.statement.length > 44 ? r.statement.slice(0, 43) + "…" : r.statement}”</button>)}
        </div>
      )}
      {options.length > 0 && (
        <div className="row-wrap mt">
          {options.map((o) => <button key={o} className={`btn sm ${value === o ? "primary" : ""}`} onClick={() => setValue(o)}>{o}</button>)}
          <input className="input" style={{ width: 200, height: 28, padding: "4px 10px" }} placeholder="or type another…" value={options.includes(value) ? "" : value} onChange={(e) => setValue(e.target.value)} />
        </div>
      )}
      <textarea className="textarea mt" placeholder={q.kind === "tacit" ? "Exact steps, commands, and when this workaround can be removed…" : "Context the successor needs (optional)…"} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="spread mt-s">
        <span className="tiny muted row"><Clock size={12} /> Becomes testimony — never auto-verified.</span>
        <button className="btn primary" disabled={busy || (needsValue ? !value.trim() : !text.trim())} onClick={submit}>{busy ? <Spinner /> : <Send size={14} />} Submit answer</button>
      </div>
    </div>
  );
}
