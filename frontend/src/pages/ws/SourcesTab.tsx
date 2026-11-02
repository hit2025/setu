import { useRef, useState } from "react";
import { Eye, FileJson, FileSpreadsheet, FileText, KeyRound, Trash2, UploadCloud } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { Badge, Drawer, LabelBadge, Modal, Spinner, fmtTime, shortHash, useToast } from "../../components/ui";
import type { Source } from "../../types";
import type { WS } from "../Workspace";

const LABELS = ["public", "team", "engineering", "finance", "confidential"];
const KIND_ICON: Record<string, any> = { csv: FileSpreadsheet, json: FileJson };

export function SourcesTab({ ws }: { ws: WS }) {
  const { system } = useAuth();
  const [over, setOver] = useState(false);
  const [pending, setPending] = useState<{ file: File; label: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<Source | null>(null);
  const [pick, setPick] = useState<{ start: number; end: number; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const add = (files: FileList | null) => {
    if (!files) return;
    setPending((p) => [...p, ...Array.from(files).map((file) => ({ file, label: "team" }))]);
  };
  const upload = async () => {
    setBusy(true);
    try {
      const labels: Record<string, string> = {};
      pending.forEach((p) => (labels[p.file.name] = p.label));
      const r = await api.upload(ws.caseData.id, pending.map((p) => p.file), labels);
      r.notes.forEach((n) => toast("info", n));
      toast("ok", `${r.added.length} source(s) imported`);
      setPending([]);
      await ws.reload();
    } catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  const relabel = async (s: Source, label: string) => {
    try { await api.relabel(s.id, label); toast("ok", `${s.filename} → ${label}. Access for dependent claims re-derived.`); await ws.reload(); }
    catch (e: any) { toast("err", e.message); }
  };
  const remove = async (s: Source) => {
    if (!confirm(`Remove ${s.filename} and every claim it supports?`)) return;
    await api.deleteSource(s.id); await ws.reload();
  };
  const openView = async (s: Source) => setView(await api.source(s.id));

  const real = ws.sources.filter((s) => s.kind !== "testimony");
  const testimony = ws.sources.filter((s) => s.kind === "testimony");

  return (
    <div className="col gap-l">
      <div className="grid g-side">
        <div className="card">
          <div className="card-head"><h3>Source manifest</h3><span className="small muted">{real.length} / 50 files · {real.reduce((n, s) => n + s.char_count, 0).toLocaleString()} / 100,000 chars</span></div>
          <table className="tbl">
            <thead><tr><th>File</th><th>Access label</th><th>Masked</th><th>Content hash</th><th>Status</th><th /></tr></thead>
            <tbody>
              {real.map((s) => {
                const Icon = KIND_ICON[s.kind] || FileText;
                const masked = Object.entries(s.masked || {});
                return (
                  <tr key={s.id}>
                    <td>
                      <div className="row"><Icon size={16} color="var(--accent)" /><div><div className="strong small">{s.filename}</div><div className="tiny muted">{s.kind} · {s.char_count.toLocaleString()} chars{s.authored_at && ` · ${s.authored_at}`}</div></div></div>
                    </td>
                    <td>
                      <select className="select sm" value={s.label} onChange={(e) => relabel(s, e.target.value)} aria-label="Access label">
                        {LABELS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </td>
                    <td>{masked.length ? masked.map(([k, v]) => <Badge key={k} tone="teal"><KeyRound size={11} /> {v} {k.replace("_", " ")}</Badge>) : <span className="tiny muted">—</span>}</td>
                    <td><span className="mono muted" title={s.content_hash}>{shortHash(s.content_hash)}</span></td>
                    <td>{s.excluded_reason ? <Badge tone="red" title={s.excluded_reason}>Excluded</Badge> : s.extracted ? <Badge tone="teal">Extracted</Badge> : <Badge>Not yet</Badge>}</td>
                    <td><div className="row" style={{ gap: 4 }}>
                      <button className="btn sm ghost icon-btn" onClick={() => openView(s)} aria-label="View"><Eye size={14} /></button>
                      <button className="btn sm ghost icon-btn" onClick={() => remove(s)} aria-label="Remove"><Trash2 size={14} /></button>
                    </div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {testimony.length > 0 && (
            <div className="card-body" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="small strong mb">Testimony sources (answers from the departing member, hashed like any other source)</div>
              <div className="row-wrap">{testimony.map((s) => <button key={s.id} className="btn sm" onClick={() => openView(s)}><FileText size={12} /> {s.filename}</button>)}</div>
            </div>
          )}
        </div>
        <div className="col">
          <div className={`dropzone ${over ? "over" : ""}`} onClick={() => input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}>
            <UploadCloud size={30} color="var(--accent)" />
            <div className="strong mt-s">Drop authorised files here</div>
            <div className="small muted">.md · .txt · .csv · .json (chat or activity exports)</div>
            <input ref={input} type="file" multiple hidden accept=".md,.markdown,.txt,.csv,.json" onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          </div>
          {pending.length > 0 && (
            <div className="card card-pad">
              <div className="col gap-s">
                {pending.map((p, i) => (
                  <div key={i} className="spread">
                    <span className="small ellipsis flex1">{p.file.name}</span>
                    <select className="select sm" value={p.label} onChange={(e) => setPending((x) => x.map((y, j) => (j === i ? { ...y, label: e.target.value } : y)))}>
                      {LABELS.map((l) => <option key={l}>{l}</option>)}
                    </select>
                  </div>
                ))}
                <button className="btn primary mt-s" onClick={upload} disabled={busy}>{busy ? <Spinner /> : <UploadCloud size={15} />} Import {pending.length} file(s)</button>
              </div>
            </div>
          )}
          <div className="card card-pad">
            <h3>What happens at import</h3>
            <ul className="small muted" style={{ paddingLeft: 18, marginBottom: 0 }}>
              <li>Secrets, connection strings, emails and phone numbers are masked <b>before</b> storage — no model ever sees them.</li>
              <li>Each file gets a raw and a canonical SHA-256 hash; citations point into the canonical text.</li>
              <li>Chat and activity JSON is normalised into timestamped lines with stable passage IDs.</li>
              <li><b>confidential</b> files are stored for the reviewer only and never extracted or released.</li>
            </ul>
            <div className="mt-s">{system?.labels.map((l) => <div key={l.label} className="row small mt-s"><LabelBadge label={l.label} /><span className="muted">{l.readers.join(", ")}</span></div>)}</div>
          </div>
        </div>
      </div>
      <Drawer open={!!view} onClose={() => setView(null)} wide title={view && <div className="row"><b>{view.filename}</b><LabelBadge label={view.label} /></div>}>
        {view && (
          <>
            <div className="row-wrap small muted mb">
              <span>canonical sha256 <span className="mono">{shortHash(view.content_hash)}</span></span>
              <span>· raw sha256 <span className="mono">{shortHash(view.raw_hash)}</span></span>
              <span>· {view.passages?.length} passages · uploaded {fmtTime(view.uploaded_at)}</span>
            </div>
            {view.kind !== "testimony" && !view.excluded_reason && (
              <div className="notice accent small mb">Select any text below to create an evidence-linked claim by hand — the fallback path when AI extraction fails or misses something.</div>
            )}
            <div className="source-view" onMouseUp={(e) => {
              if (view.kind === "testimony" || view.excluded_reason) return;
              const sel = window.getSelection();
              const box = e.currentTarget;
              if (!sel || sel.isCollapsed || !box.contains(sel.anchorNode)) return;
              const r = sel.getRangeAt(0);
              const pre = document.createRange();
              pre.setStart(box, 0);
              pre.setEnd(r.startContainer, r.startOffset);
              const start = pre.toString().length;
              const text = r.toString();
              if (text.trim()) setPick({ start, end: start + text.length, text });
            }}>{view.content}</div>
          </>
        )}
      </Drawer>
      {view && pick && (
        <ManualClaim caseId={ws.caseData.id} source={view} pick={pick} onClose={() => setPick(null)}
          onDone={async () => { setPick(null); await ws.reload(); toast("ok", "Manual claim created, anchored and accepted"); }} />
      )}
    </div>
  );
}

const CTYPES = ["decision", "owner", "task", "deadline", "dependency", "risk", "contact", "status"];

function ManualClaim({ caseId, source, pick, onClose, onDone }: {
  caseId: string; source: Source; pick: { start: number; end: number; text: string }; onClose: () => void; onDone: () => void;
}) {
  const [f, setF] = useState({ ctype: "decision", subject: "", value: pick.text.trim().slice(0, 120) });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async () => {
    setBusy(true);
    try {
      await api.manualClaim(caseId, { source_id: source.id, start: pick.start, end: pick.end, ctype: f.ctype, subject: f.subject, value: f.value });
      onDone();
    } catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title="Create claim from selected evidence">
      <div className="col">
        <div className="quote">{pick.text}</div>
        <div className="tiny muted">{source.filename} · characters {pick.start}–{pick.end} · this exact span becomes the citation</div>
        <div className="grid g2">
          <label className="field">Type
            <select className="select" value={f.ctype} onChange={(e) => setF({ ...f, ctype: e.target.value })}>
              {CTYPES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="field">Subject (what it is about)<input className="input" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} placeholder="e.g. Hosting platform" /></label>
        </div>
        <label className="field">Value<input className="input" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></label>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || !f.subject.trim() || !f.value.trim()} onClick={submit}>{busy ? <Spinner /> : null} Create claim</button>
        </div>
      </div>
    </Modal>
  );
}
