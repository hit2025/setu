import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, ExternalLink, Fingerprint, Lock, ShieldCheck, XCircle } from "lucide-react";
import { api } from "../../api";
import { Badge, Spinner, Stat, fmtTime, shortHash, useToast } from "../../components/ui";
import type { Gate, HandoverView, Snapshot } from "../../types";
import type { WS } from "../Workspace";

export function ReleaseTab({ ws }: { ws: WS }) {
  const id = ws.caseData.id;
  const [gate, setGate] = useState<Gate | null>(null);
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Record<string, HandoverView | null>>({});
  const toast = useToast();

  const load = async () => {
    const [g, s] = await Promise.all([api.gate(id), api.snapshots(id)]);
    setGate(g); setSnaps(s);
    if (s.length) {
      const [e, c] = await Promise.all([api.handover(id, undefined, "engineer"), api.handover(id, undefined, "coordinator")]);
      setPreview({ engineer: e, coordinator: c });
    }
  };
  useEffect(() => { load().catch((e) => toast("err", e.message)); }, [ws.caseData.counts.pending, ws.caseData.counts.versions]);

  const approve = async () => {
    setBusy(true);
    try {
      const r = await api.approve(id, note);
      toast("ok", `Version ${r.version} approved and released (sha256 ${r.hash.slice(0, 10)}…)`);
      setNote("");
      await ws.reload(); await load();
    } catch (e: any) {
      toast("err", e.detail?.issues ? e.detail.issues.map((i: any) => i.message).join(" ") : e.message);
      await load();
    } finally { setBusy(false); }
  };

  return (
    <div className="col gap-l">
      <div className="grid g-side">
        <div className="card">
          <div className="card-head"><h3 className="row"><ShieldCheck size={16} color="var(--accent)" /> Approval gate</h3>{gate && (gate.ok ? <Badge tone="teal">Ready to approve</Badge> : <Badge tone="red">Blocked</Badge>)}</div>
          <div className="card-body col">
            {!gate ? <div className="row"><Spinner /> Checking…</div> : (
              <>
                {[
                  { ok: gate.counts.pending === 0, t: "Every claim has a reviewer decision", d: `${gate.counts.pending} pending` },
                  { ok: gate.counts.open_conflicts === 0, t: "Every conflict has a winner or is explicitly released as unresolved", d: `${gate.counts.open_conflicts} open` },
                  { ok: !gate.issues.some((i) => i.code === "invalid_evidence"), t: "Every accepted claim still has a valid exact anchor and source hash", d: "re-verified now" },
                  { ok: !gate.issues.some((i) => i.code === "empty"), t: "At least one claim is accepted", d: `${gate.counts.accepted + gate.counts.edited} accepted` },
                  ...(snaps.length ? [{ ok: !gate.issues.some((i) => i.code === "no_changes"), t: `Something changed since v${snaps[0].version}`, d: "versions are immutable" }] : []),
                ].map((r) => (
                  <div key={r.t} className="row">
                    {r.ok ? <CheckCircle2 size={18} color="var(--teal)" /> : <XCircle size={18} color="var(--red)" />}
                    <div className="flex1 small">{r.t}</div>
                    <span className="tiny muted">{r.d}</span>
                  </div>
                ))}
                <div className="divider" />
                <label className="field">Release note (optional)<input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Hosting confirmed with Rohan; release date left open" /></label>
                <div className="spread">
                  <span className="tiny muted">Approval freezes an immutable, hashed version. Recipients can only ever read approved versions.</span>
                  <button className="btn primary lg" disabled={!gate.ok || busy} onClick={approve}>{busy ? <Spinner /> : <Lock size={16} />} Approve & release v{(snaps[0]?.version ?? 0) + 1}</button>
                </div>
                {!gate.ok && <div className="row-wrap">
                  {gate.counts.open_conflicts > 0 && <button className="btn sm" onClick={() => ws.go("verify")}>Resolve conflicts</button>}
                  {gate.counts.pending > 0 && <button className="btn sm" onClick={() => ws.go("review")}>Review pending claims</button>}
                </div>}
              </>
            )}
          </div>
        </div>
        <div className="grid" style={{ alignContent: "start" }}>
          <Stat label="Verified / edited" value={(gate?.counts.accepted ?? 0) + (gate?.counts.edited ?? 0)} tone="teal" />
          <Stat label="Released as unresolved" value={gate?.counts.unresolved ?? 0} tone="amber" />
          <Stat label="Rejected (never released)" value={gate?.counts.rejected ?? 0} />
        </div>
      </div>

      {snaps.length > 0 && (
        <div className="card">
          <div className="card-head"><h3>Permission preview · latest version</h3><span className="small muted">Computed by the same server-side filter recipients use</span></div>
          <div className="card-body grid g2">
            {(["engineer", "coordinator"] as const).map((r) => {
              const v = preview[r];
              return (
                <div key={r} className="side">
                  <div className="spread"><b>{r === "engineer" ? "Meera · incoming engineer" : "Ananya · incoming coordinator"}</b>
                    <Link className="btn sm" to={`/handover/${id}?as=${r}`}><ExternalLink size={12} /> Open preview</Link></div>
                  {v ? (
                    <>
                      <div className="row-wrap">
                        <Badge>{v.stats.claims} claims</Badge><Badge>{v.stats.actions} actions</Badge><Badge tone="teal">{v.stats.ready} ready</Badge>
                        <Badge tone="red">{v.stats.blocked} blocked / no owner</Badge><Badge tone="amber">{v.stats.unresolved} unresolved</Badge>
                      </div>
                      <div className="tiny muted">Sources visible: {v.sources.map((s) => s.filename).join(", ") || "none"}</div>
                      <div className="tiny muted">First correct action: <b style={{ color: "var(--text-2)" }}>{v.first_action?.title || "—"}</b></div>
                    </>
                  ) : <Spinner />}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Version history</h3><span className="small muted">Immutable, content-hashed snapshots</span></div>
        {snaps.length === 0 ? <div className="card-body small muted">No version approved yet.</div> : (
          <table className="tbl">
            <thead><tr><th>Version</th><th>Content hash</th><th>Approved</th><th>Contents</th><th>Change vs previous</th><th>Receipts</th></tr></thead>
            <tbody>
              {snaps.map((s) => (
                <tr key={s.id}>
                  <td><Badge tone="accent">v{s.version}</Badge>{s.note && <div className="tiny muted mt-s">{s.note}</div>}</td>
                  <td><span className="mono muted row" style={{ gap: 4 }}><Fingerprint size={12} /> {shortHash(s.hash)}</span></td>
                  <td className="small">{s.approved_by} · {fmtTime(s.approved_at)}</td>
                  <td className="small">{s.claims} claims · {s.actions} actions</td>
                  <td className="small">{s.diff ? <><span style={{ color: "var(--teal)" }}>+{s.diff.added}</span> / <span style={{ color: "var(--red)" }}>−{s.diff.removed}</span></> : "—"}</td>
                  <td>{s.receipts.length ? s.receipts.map((r) => <Badge key={r.user_id} tone="teal" title={`view hash ${r.view_hash}`}><CheckCircle2 size={11} /> {r.user_id} · {fmtTime(r.at)}</Badge>) : <span className="tiny muted">awaiting</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
