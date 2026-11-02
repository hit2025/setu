import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BadgeCheck, CheckCircle2, Eye, FileText, Fingerprint, HelpCircle, Lightbulb, PauseCircle, Phone, Search, ShieldAlert, Sparkles, Users } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ActionCard } from "../components/ActionCard";
import { EvidenceDrawer } from "../components/Evidence";
import { Shell } from "../components/Shell";
import { Badge, Empty, LabelBadge, ROLE_LABEL, Spinner, Stat, fmtDate, fmtTime, shortHash, useToast } from "../components/ui";
import type { Claim, HandoverView } from "../types";

export function Handover() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const asRole = user?.role === "reviewer" ? sp.get("as") || "engineer" : undefined;
  const version = sp.get("v") ? Number(sp.get("v")) : undefined;
  const [view, setView] = useState<HandoverView | null>(null);
  const [err, setErr] = useState("");
  const [claim, setClaim] = useState<Claim | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ score: number; claim: Claim }[] | null>(null);
  const [acking, setAcking] = useState(false);
  const toast = useToast();

  const load = () => api.handover(id, version, asRole).then((v) => { setView(v); setErr(""); }).catch((e) => setErr(e.message));
  useEffect(() => { setView(null); load(); }, [id, version, asRole]);
  const claims = useMemo(() => new Map((view?.claims ?? []).map((c) => [c.id, c])), [view]);

  useEffect(() => {
    if (!q.trim()) { setHits(null); return; }
    const t = setTimeout(() => api.search(id, q, version, asRole).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(t);
  }, [q, id, version, asRole]);

  const ack = async () => {
    if (!view) return;
    setAcking(true);
    try { await api.ack(id, view.version); toast("ok", `Receipt of v${view.version} acknowledged`); load(); }
    catch (e: any) { toast("err", e.message); } finally { setAcking(false); }
  };

  if (err) return (
    <Shell crumbs={<b>Handover</b>}>
      <div className="card"><Empty icon={<ShieldAlert size={32} />} title="No approved handover is available">{err}</Empty></div>
    </Shell>
  );
  if (!view) return <Shell crumbs={<b>Handover</b>}><div className="row"><Spinner /> Loading the approved, role-filtered handover…</div></Shell>;

  const roleName = ROLE_LABEL[view.role] || view.role;
  const mode = { kind: "handover" as const, caseId: id, version: view.version, asRole };
  const fa = view.first_action;

  return (
    <Shell crumbs={<><span>{view.case.project}</span><span>/</span><b>Handover v{view.version}</b></>}
      actions={view.versions.length > 1 && (
        <select className="select sm" value={view.version} onChange={(e) => setSp({ ...(asRole ? { as: asRole } : {}), v: e.target.value })} aria-label="Version">
          {view.versions.map((v) => <option key={v} value={v}>v{v}{v === view.latest_version ? " (latest)" : ""}</option>)}
        </select>
      )}>
      {view.preview && (
        <div className="notice accent mb">
          <Eye size={16} />
          <div className="flex1">Reviewer preview — this is exactly what the server returns to the <b>{roleName}</b>. Nothing outside this role's access is in the response.</div>
          <div className="row">
            {["engineer", "coordinator"].map((r) => <button key={r} className={`btn sm ${asRole === r ? "primary" : ""}`} onClick={() => setSp({ as: r })}>{ROLE_LABEL[r]}</button>)}
            <Link className="btn sm" to={`/cases/${id}?tab=release`}><ArrowLeft size={12} /> Workspace</Link>
          </div>
        </div>
      )}
      {view.version !== view.latest_version && <div className="notice amber mb"><AlertTriangle size={16} /> You are viewing v{view.version}. A newer approved version (v{view.latest_version}) exists.</div>}

      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <div className="row-wrap"><Badge tone="accent">{view.case.project}</Badge><Badge tone="teal"><BadgeCheck size={12} /> Approved v{view.version}</Badge><Badge>{roleName} view</Badge></div>
          <h1 className="mt-s">Handover from {view.case.departing}</h1>
          <div className="small muted mt-s">
            Approved by {view.approved_by} · {fmtTime(view.approved_at)} · <span className="mono"><Fingerprint size={11} /> {shortHash(view.snapshot_hash)}</span>
            {view.note && <> · “{view.note}”</>}
          </div>
        </div>
        {!view.preview && (view.receipt ? (
          <div className="card card-pad" style={{ padding: 12, borderColor: "rgba(45,212,191,.4)" }}>
            <div className="row small strong" style={{ color: "var(--teal)" }}><CheckCircle2 size={16} /> Receipt acknowledged</div>
            <div className="tiny muted mt-s">{fmtTime(view.receipt.at)} · view <span className="mono">{shortHash(view.receipt.view_hash)}</span></div>
          </div>
        ) : (
          <button className="btn primary lg" onClick={ack} disabled={acking}>{acking ? <Spinner /> : <CheckCircle2 size={16} />} Acknowledge receipt of v{view.version}</button>
        ))}
      </div>

      <div className="hero-action mt">
        <div className="row small" style={{ color: "#74eedb" }}><Sparkles size={15} /> Your first correct action</div>
        {fa ? (
          <div className="spread mt-s" style={{ alignItems: "flex-start" }}>
            <div className="flex1">
              <h2 style={{ fontSize: 22 }}>{fa.title}</h2>
              <div className="small muted mt-s">Owner {fa.owner} · due {fmtDate(fa.due)} · every check passed: staying owner, agreed date, exact evidence, prerequisites satisfied.</div>
            </div>
            <button className="btn" onClick={() => { const c = fa.claim_ids.map((x) => claims.get(x)).find(Boolean); c && setClaim(c); }}><FileText size={14} /> Evidence</button>
          </div>
        ) : (
          <div className="mt-s">
            <h2>No action is fully ready yet.</h2>
            <div className="small muted mt-s">Every visible action is missing an owner or has an unmet prerequisite — see the blockers below. SETU shows this honestly instead of guessing.</div>
          </div>
        )}
      </div>

      <div className="grid g4 mt">
        <Stat label="Verified claims" value={view.stats.claims} />
        <Stat label="Ready actions" value={view.stats.ready} tone="teal" />
        <Stat label="Blocked / need owner" value={view.stats.blocked} tone={view.stats.blocked ? "red" : undefined} />
        <Stat label="Unresolved items" value={view.stats.unresolved} tone={view.stats.unresolved ? "amber" : undefined} />
      </div>

      <div className="grid g-side mt-l" style={{ alignItems: "start" }}>
        <div className="col gap-l">
          <section>
            <h2 className="mb">Ranked next actions</h2>
            {view.actions.length ? <div className="col">{view.actions.map((a) => <ActionCard key={a.key} a={a} claims={claims} onOpen={setClaim} />)}</div>
              : <div className="card"><Empty title="No actions released to your role" /></div>}
          </section>

          {view.unresolved.length > 0 && (
            <section>
              <h2 className="mb row"><PauseCircle size={18} color="var(--amber)" /> Unresolved — confirm before acting</h2>
              <div className="col">
                {view.unresolved.map((u) => (
                  <div key={u.group} className="notice amber" style={{ flexDirection: "column" }}>
                    <div className="strong" style={{ textTransform: "capitalize" }}>{u.attribute.replace(/^(\w+): /, "$1 · ")}</div>
                    <div className="small">The reviewer released this as unresolved. Sources disagree:</div>
                    <div className="row-wrap">
                      {u.claims.map((c) => <button key={c.id} className="btn sm" onClick={() => setClaim(c)}>“{c.value}” · {c.evidence[0]?.source_name}</button>)}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb">Verified decisions</h2>
            <div className="card">
              <table className="tbl">
                <tbody>
                  {view.decisions.map((d) => (
                    <tr key={d.id} className="clickable" onClick={() => setClaim(d)}>
                      <td className="small muted" style={{ width: "38%", textTransform: "capitalize" }}>{d.subject}</td>
                      <td className="strong">{d.value}{d.review_status === "edited" && <Badge tone="amber">edited</Badge>}</td>
                      <td style={{ textAlign: "right" }}><span className="tiny muted">{d.evidence.map((e) => e.source_name).join(", ")}</span></td>
                    </tr>
                  ))}
                  {view.proposals.map((d) => (
                    <tr key={d.id} className="clickable" onClick={() => setClaim(d)}>
                      <td className="small muted">Proposal</td>
                      <td className="small">{d.value} <Badge tone="amber">not a decision</Badge></td>
                      <td style={{ textAlign: "right" }}><span className="tiny muted">{d.evidence[0]?.source_name}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!view.decisions.length && <Empty title="No decisions in your view" />}
            </div>
          </section>

          {view.risks.length > 0 && (
            <section>
              <h2 className="mb row"><Lightbulb size={18} color="var(--amber)" /> Risks & tacit knowledge</h2>
              <div className="col">
                {view.risks.map((r) => (
                  <div key={r.id} className="claim" style={{ cursor: "pointer" }} onClick={() => setClaim(r)}>
                    <div className="row-wrap">{r.modality === "tacit" ? <Badge tone="pink">Tacit workaround</Badge> : r.ctype === "note" ? <Badge tone="pink">Knowledge note (verified testimony)</Badge> : <Badge tone="red">Risk</Badge>}{r.labels.map((l) => <LabelBadge key={l} label={l} />)}</div>
                    <div className="small">{r.value}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="col gap-l">
          <div className="card card-pad">
            <div className="row"><Search size={15} color="var(--muted)" /><input className="input" placeholder="Search this handover…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
            <div className="tiny muted mt-s">Searches only the claims released to your role.</div>
            {hits && (
              <div className="col gap-s mt">
                {hits.length === 0 && <div className="small muted">No matches in your view.</div>}
                {hits.map((h) => (
                  <button key={h.claim.id} className="nav-item" style={{ alignItems: "flex-start" }} onClick={() => setClaim(h.claim)}>
                    <Badge>{h.claim.ctype}</Badge><span className="small">{h.claim.statement}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-head"><h3 className="row"><Users size={15} /> Ownership map</h3></div>
            <div className="card-body col gap-s">
              {view.owners.filter((o) => o.review_status !== "unresolved").map((o) => (
                <div key={o.id} className="spread" style={{ cursor: "pointer" }} onClick={() => setClaim(o)}>
                  <span className="small ellipsis flex1" title={o.subject}>{o.subject}</span>
                  <Badge tone={o.value === view.case.departing ? "amber" : "teal"}>{o.value}</Badge>
                </div>
              ))}
              {view.transfers.length > 0 && <div className="notice amber small mt-s">{view.transfers.length} area(s) still owned by {view.case.departing} — ask the reviewer who takes over.</div>}
            </div>
          </div>

          {view.contacts.length > 0 && (
            <div className="card">
              <div className="card-head"><h3 className="row"><Phone size={15} /> Who to ask</h3></div>
              <div className="card-body col gap-s">
                {view.contacts.map((c) => (
                  <div key={c.id} className="spread" style={{ cursor: "pointer" }} onClick={() => setClaim(c)}>
                    <span className="small">{c.subject}</span><Badge tone="pink">{c.value}</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-head"><h3>Timeline</h3></div>
            <div className="card-body">
              <div className="timeline">
                {view.timeline.map((e, i) => (
                  <div key={i} className={`tl-item ${e.kind} ${e.conflict ? "conflict" : ""}`} style={{ cursor: "pointer" }} onClick={() => { const c = claims.get(e.claim_id); c && setClaim(c); }}>
                    <div className="tiny muted mono">{fmtDate(e.date)} · {e.kind}</div>
                    <div className="small">{e.text}</div>
                  </div>
                ))}
                {!view.timeline.length && <div className="small muted">No dated items.</div>}
              </div>
            </div>
          </div>

          {view.open_questions.length > 0 && (
            <div className="card">
              <div className="card-head"><h3 className="row"><HelpCircle size={15} /> Still-open questions</h3></div>
              <div className="card-body col gap-s">{view.open_questions.map((oq) => <div key={oq.id} className="small muted">• {oq.prompt}</div>)}</div>
            </div>
          )}

          <div className="card card-pad">
            <h3>Sources behind your view</h3>
            <div className="col gap-s mt-s">
              {view.sources.map((s) => (
                <div key={s.id} className="spread"><span className="small row"><FileText size={13} /> {s.filename}</span><LabelBadge label={s.label} /></div>
              ))}
            </div>
            <div className="tiny muted mt">Sources outside your access are not listed — not even their names.</div>
          </div>
        </aside>
      </div>
      <EvidenceDrawer claim={claim} mode={mode} onClose={() => setClaim(null)} />
    </Shell>
  );
}
