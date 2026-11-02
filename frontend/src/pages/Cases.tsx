import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpenCheck, CheckCircle2, FolderPlus, Inbox, Plus, Sparkles, Trash2 } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Shell } from "../components/Shell";
import { Badge, Empty, Modal, Spinner, fmtDate, useToast } from "../components/ui";
import type { Case } from "../types";

const STAGES = ["Connect", "Reconstruct", "Verify", "Review", "Handover"];

export function Cases() {
  const { user } = useAuth();
  const [cases, setCases] = useState<Case[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const toast = useToast();
  const nav = useNavigate();
  const load = () => api.cases().then(setCases).catch((e) => toast("err", e.message));
  useEffect(() => { load(); }, [user?.id]);
  if (!user) return null;

  const demo = async () => {
    setBusy(true);
    try { const c = await api.createDemo(); toast("ok", "Demo case created with 7 labelled sources"); nav(`/cases/${c.id}`); }
    catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  const remove = async (c: Case) => {
    if (!confirm(`Delete case “${c.name}”? This removes all its sources, claims and versions.`)) return;
    await api.deleteCase(c.id); load();
  };

  const isReviewer = user.role === "reviewer";
  const isRecipient = user.role === "engineer" || user.role === "coordinator";
  const title = isReviewer ? "Handover cases" : user.role === "departing" ? "Your handover interview" : "Handovers for you";
  const lead = isReviewer
    ? "Each case is one departure. Import authorised sources, reconstruct the project state, review it and release a role-filtered handover."
    : user.role === "departing"
      ? "SETU has pre-filled a claim ledger from the team's records. You only answer the questions it could not resolve from evidence."
      : "Approved handovers released to your role. Everything you see was verified by the reviewer and filtered for your access level.";

  return (
    <Shell crumbs={<b>{title}</b>} actions={isReviewer && (
      <>
        <button className="btn" onClick={() => setNewOpen(true)}><Plus size={15} /> New case</button>
        <button className="btn primary" onClick={demo} disabled={busy}>{busy ? <Spinner /> : <Sparkles size={15} />} Load CampusConnect demo</button>
      </>
    )}>
      <h1>{title}</h1>
      <p className="lead mt-s">{lead}</p>
      {cases === null ? <div className="row mt-l"><Spinner /> Loading…</div> : cases.length === 0 ? (
        <div className="card mt-l">
          {isReviewer ? (
            <Empty icon={<FolderPlus size={34} />} title="No handover cases yet">
              <div className="col" style={{ alignItems: "center" }}>
                Start with the synthetic CampusConnect departure — it takes one click.
                <button className="btn primary lg mt" onClick={demo} disabled={busy}>{busy ? <Spinner /> : <Sparkles size={16} />} Load CampusConnect demo case</button>
              </div>
            </Empty>
          ) : (
            <Empty icon={isRecipient ? <BookOpenCheck size={34} /> : <Inbox size={34} />} title={isRecipient ? "Nothing has been released to you yet" : "No handover involves you yet"}>
              {isRecipient ? "A handover appears here only after the reviewer approves a version. Switch to Dev (reviewer) to create and approve one." : "Switch to Dev (reviewer) and load the demo case first."}
            </Empty>
          )}
        </div>
      ) : (
        <div className="grid g2 mt-l">
          {cases.map((c) => (
            <div key={c.id} className="card" style={{ display: "flex", flexDirection: "column" }}>
              <div className="card-body" style={{ flex: 1 }}>
                <div className="spread">
                  <Badge tone="accent">{c.project}</Badge>
                  {c.latest_version ? <Badge tone="teal"><CheckCircle2 size={12} /> v{c.latest_version} released</Badge> : <Badge>{c.status.replace("_", " ")}</Badge>}
                </div>
                <h2 className="mt">{c.name}</h2>
                <div className="small muted mt-s">Departing: <b style={{ color: "var(--text-2)" }}>{c.departing?.name}</b>{c.departure_date && <> · leaves {fmtDate(c.departure_date)}</>} · reviewer {c.reviewer?.name}</div>
                {isReviewer || user.role === "departing" ? (
                  <>
                    <div className="row mt" style={{ gap: 4 }}>
                      {STAGES.map((s, i) => (
                        <div key={s} className="flex1">
                          <div style={{ height: 5, borderRadius: 4, background: i + 1 < c.stage ? "var(--teal)" : i + 1 === c.stage ? "var(--accent)" : "var(--surface-3)" }} />
                          <div className="tiny muted mt-s">{s}</div>
                        </div>
                      ))}
                    </div>
                    <div className="row-wrap mt">
                      <Badge>{c.counts.sources} sources</Badge>
                      <Badge>{c.counts.claims} claims</Badge>
                      {!!c.counts.pending && <Badge tone="blue">{c.counts.pending} to review</Badge>}
                      {!!c.counts.conflicts && <Badge tone="red">{c.counts.conflicts} conflicts</Badge>}
                      {!!c.counts.open_questions && <Badge tone="pink">{c.counts.open_questions} open questions</Badge>}
                    </div>
                  </>
                ) : (
                  <div className="row-wrap mt">
                    {c.acknowledged ? <Badge tone="teal"><CheckCircle2 size={12} /> Acknowledged</Badge> : <Badge tone="amber">Awaiting your acknowledgement</Badge>}
                  </div>
                )}
              </div>
              <div className="card-head" style={{ borderTop: "1px solid var(--border)", borderBottom: "none" }}>
                <Link to={isRecipient ? `/handover/${c.id}` : `/cases/${c.id}`} className="btn primary sm">
                  {isRecipient ? "Open handover" : user.role === "departing" ? "Answer questions" : "Open workspace"} <ArrowRight size={14} />
                </Link>
                {isReviewer && <button className="btn ghost sm" onClick={() => remove(c)} aria-label="Delete case"><Trash2 size={14} /></button>}
              </div>
            </div>
          ))}
        </div>
      )}
      <NewCaseModal open={newOpen} onClose={() => setNewOpen(false)} onCreated={(c) => nav(`/cases/${c.id}`)} />
    </Shell>
  );
}

function NewCaseModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (c: Case) => void }) {
  const [f, setF] = useState({ name: "", project: "", description: "", departing_user_id: "rohan", departure_date: "", eng: true, coord: true });
  const toast = useToast();
  const submit = async () => {
    try {
      const c = await api.createCase({
        name: f.name, project: f.project, description: f.description, departing_user_id: f.departing_user_id, departure_date: f.departure_date,
        recipient_roles: [f.eng && "engineer", f.coord && "coordinator"].filter(Boolean),
      });
      onCreated(c);
    } catch (e: any) { toast("err", e.message); }
  };
  return (
    <Modal open={open} onClose={onClose} title="New handover case">
      <div className="col">
        <label className="field">Case name<input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Backend lead handover" /></label>
        <label className="field">Project<input className="input" value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })} placeholder="e.g. CampusConnect" /></label>
        <label className="field">Context (optional)<textarea className="textarea" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <div className="grid g2">
          <label className="field">Departing member
            <select className="select" value={f.departing_user_id} onChange={(e) => setF({ ...f, departing_user_id: e.target.value })}>
              <option value="rohan">Rohan Das</option>
            </select>
          </label>
          <label className="field">Departure date<input className="input" type="date" value={f.departure_date} onChange={(e) => setF({ ...f, departure_date: e.target.value })} /></label>
        </div>
        <div className="field">Recipients
          <div className="row">
            <label className="row small"><input type="checkbox" checked={f.eng} onChange={(e) => setF({ ...f, eng: e.target.checked })} /> Incoming engineer</label>
            <label className="row small"><input type="checkbox" checked={f.coord} onChange={(e) => setF({ ...f, coord: e.target.checked })} /> Incoming coordinator</label>
          </div>
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={f.name.length < 3 || f.project.length < 2} onClick={submit}>Create case</button>
        </div>
      </div>
    </Modal>
  );
}
