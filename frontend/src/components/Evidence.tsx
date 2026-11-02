import { useEffect, useRef, useState } from "react";
import { FileText, Fingerprint, Lock, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "../api";
import type { Claim, Source } from "../types";
import { Badge, ClaimStateBadge, Drawer, LabelBadge, Spinner, TYPE_TONE, shortHash } from "./ui";

type Mode = { kind: "workspace" } | { kind: "handover"; caseId: string; version?: number; asRole?: string };

export function EvidenceDrawer({ claim, mode, onClose }: { claim: Claim | null; mode: Mode; onClose: () => void }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => setIdx(0), [claim?.id]);
  if (!claim) return null;
  const ev = claim.evidence[idx];
  return (
    <Drawer open={!!claim} onClose={onClose} wide title={
      <div className="col" style={{ gap: 4 }}>
        <div className="row-wrap"><Badge tone={TYPE_TONE[claim.ctype]}>{claim.ctype}</Badge><ClaimStateBadge c={claim} />
          {claim.modality === "proposal" && <Badge tone="amber">Proposal — not a decision</Badge>}
          {claim.modality === "tacit" && <Badge tone="pink">Tacit knowledge</Badge>}
        </div>
        <div className="strong">{claim.statement}</div>
      </div>
    }>
      {claim.original_value && (
        <div className="notice amber mb small">Reviewer changed the value from <b>&nbsp;“{claim.original_value}”&nbsp;</b> to <b>&nbsp;“{claim.value}”</b>.{claim.review_note && <> Note: {claim.review_note}</>}</div>
      )}
      {!claim.original_value && claim.review_note && <div className="notice mb small">{claim.review_note}</div>}
      {claim.evidence.length > 1 && (
        <div className="row-wrap mb">
          <span className="small muted">{claim.evidence.length} supporting citations:</span>
          {claim.evidence.map((e, i) => (
            <button key={e.id} className={`btn sm ${i === idx ? "primary" : ""}`} onClick={() => setIdx(i)}>{e.source_name}</button>
          ))}
        </div>
      )}
      {ev && (mode.kind === "workspace" ? <WorkspaceSpan claim={claim} evIdx={idx} /> : <HandoverSpan claim={claim} evIdx={idx} mode={mode} />)}
    </Drawer>
  );
}

function SpanMeta({ filename, label, hash, start, end, intact }: { filename: string; label: string; hash: string; start: number; end: number; intact: boolean }) {
  return (
    <div className="card card-pad mb" style={{ padding: 14 }}>
      <div className="spread">
        <div className="row"><FileText size={16} color="var(--accent)" /><b>{filename}</b><LabelBadge label={label} /></div>
        {intact ? <Badge tone="teal"><ShieldCheck size={12} /> Exact anchor verified</Badge> : <Badge tone="red"><ShieldAlert size={12} /> Source changed since approval</Badge>}
      </div>
      <div className="row-wrap mt-s tiny muted">
        <span className="row" style={{ gap: 4 }}><Fingerprint size={12} /> sha256 <span className="mono">{shortHash(hash)}</span></span>
        <span>· characters <span className="mono">{start}–{end}</span></span>
      </div>
    </div>
  );
}

function WorkspaceSpan({ claim, evIdx }: { claim: Claim; evIdx: number }) {
  const ev = claim.evidence[evIdx];
  const [src, setSrc] = useState<Source | null>(null);
  const [err, setErr] = useState("");
  const markRef = useRef<HTMLElement>(null);
  useEffect(() => {
    setSrc(null); setErr("");
    api.source(ev.source_id).then(setSrc).catch((e) => setErr(e.message));
  }, [ev.source_id]);
  useEffect(() => { markRef.current?.scrollIntoView({ block: "center" }); }, [src, evIdx]);
  if (err) return <div className="notice red"><Lock size={16} /> {err}</div>;
  if (!src?.content) return <div className="row"><Spinner /> Loading source…</div>;
  const c = src.content;
  const intact = c.slice(ev.start, ev.end) === ev.quote && src.content_hash === ev.source_hash;
  return (
    <>
      <SpanMeta filename={src.filename} label={src.label} hash={src.content_hash} start={ev.start} end={ev.end} intact={intact} />
      <div className="source-view" style={{ maxHeight: "60vh", overflow: "auto" }}>
        {c.slice(0, ev.start)}<mark ref={markRef} className="hl">{c.slice(ev.start, ev.end)}</mark>{c.slice(ev.end)}
      </div>
    </>
  );
}

function HandoverSpan({ claim, evIdx, mode }: { claim: Claim; evIdx: number; mode: Extract<Mode, { kind: "handover" }> }) {
  const ev = claim.evidence[evIdx];
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setData(null); setErr("");
    api.citation(mode.caseId, claim.id, ev.id, mode.version, mode.asRole).then(setData).catch((e) => setErr(e.message));
  }, [claim.id, ev.id]);
  if (err) return <div className="notice red"><Lock size={16} /> Access re-checked on open: {err}</div>;
  if (!data) return <div className="row"><Spinner /> Re-checking access and loading citation…</div>;
  return (
    <>
      <SpanMeta filename={data.source.filename} label={data.source.label} hash={data.source.content_hash} start={data.start} end={data.end} intact={data.intact} />
      <div className="source-view">
        {data.before && <span className="muted">…{data.before}</span>}<mark className="hl">{data.quote}</mark>{data.after && <span className="muted">{data.after}…</span>}
      </div>
      <div className="tiny muted mt-s">Access to this citation was re-checked against the current policy when you opened it.</div>
    </>
  );
}

export function CitationChips({ claim, onOpen }: { claim: Claim; onOpen: () => void }) {
  return (
    <div className="row-wrap">
      {claim.evidence.map((e) => (
        <button key={e.id} className="btn sm ghost" onClick={onOpen} title={e.quote} style={{ border: "1px solid var(--border)" }}>
          <FileText size={12} /> {e.source_name}
          {!e.valid && <ShieldAlert size={12} color="var(--red)" />}
        </button>
      ))}
    </div>
  );
}
