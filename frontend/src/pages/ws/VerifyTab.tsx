import { Fragment, useMemo, useState } from "react";
import { CheckCircle2, GitCompareArrows, HelpCircle, Network, PauseCircle, RotateCcw, Trophy, UserRoundCog } from "lucide-react";
import { api } from "../../api";
import { ActionCard } from "../../components/ActionCard";
import { DepGraph } from "../../components/DepGraph";
import { useSwitchPersona } from "../../components/Shell";
import { Badge, Empty, LabelBadge, fmtDate, fmtTime, useToast } from "../../components/ui";
import type { Claim, Conflict } from "../../types";
import type { WS } from "../Workspace";

const Q_KIND: Record<string, { label: string; tone: string }> = {
  conflict: { label: "Conflict", tone: "red" }, missing_owner: { label: "Missing owner", tone: "amber" },
  owner_leaving: { label: "Owner leaving", tone: "amber" }, unknown_prereq: { label: "Unknown prerequisite", tone: "red" },
  tacit: { label: "Tacit knowledge", tone: "pink" },
};

export function VerifyTab({ ws }: { ws: WS }) {
  const [graph, setGraph] = useState(false);
  const switchTo = useSwitchPersona();
  const claims = useMemo(() => new Map((ws.ledger?.claims ?? []).map((c) => [c.id, c])), [ws.ledger]);
  if (!ws.ledger || !ws.ledger.claims.length) return <div className="card"><Empty title="Nothing to verify yet">Run reconstruction first.</Empty></div>;
  const conflicts = [...ws.ledger.conflicts].sort((a, b) => (a.state === "open" ? -1 : 1) - (b.state === "open" ? -1 : 1));
  const actions = ws.ledger.actions;
  const openQ = ws.questions.filter((q) => q.status === "open");
  const doneQ = ws.questions.filter((q) => q.status !== "open");

  return (
    <div className="col gap-l">
      <section>
        <div className="spread mb">
          <div>
            <h2 className="row"><GitCompareArrows size={18} color="var(--red)" /> Conflicting evidence</h2>
            <div className="small muted mt-s">Incompatible claims stay side by side. SETU never lets a newer timestamp silently win — a human decides, or releases it as explicitly unresolved.</div>
          </div>
        </div>
        {conflicts.length ? <div className="col">{conflicts.map((g) => <ConflictCard key={g.group} g={g} claims={claims} ws={ws} />)}</div>
          : <div className="card"><Empty title="No conflicts detected" /></div>}
      </section>

      <section>
        <div className="spread mb">
          <div>
            <h2 className="row"><Network size={18} color="var(--teal)" /> Readiness rehearsal</h2>
            <div className="small muted mt-s">Every next action is checked for a staying owner, an agreed date, exact evidence and satisfied direct prerequisites — before anything is handed over.</div>
          </div>
          <button className="btn sm" onClick={() => setGraph((x) => !x)}><Network size={13} /> {graph ? "Hide" : "Show"} dependency graph</button>
        </div>
        {graph && <div className="mb"><DepGraph actions={actions} /></div>}
        <div className="col">{actions.map((a) => <ActionCard key={a.key} a={a} claims={claims} onOpen={ws.openClaim} />)}</div>
      </section>

      <div className="grid g2">
        <section className="card">
          <div className="card-head">
            <h3 className="row"><HelpCircle size={16} color="var(--pink)" /> Gap questions ({openQ.length} open)</h3>
            <button className="btn sm primary" onClick={() => switchTo("rohan")}><UserRoundCog size={13} /> Answer as Rohan</button>
          </div>
          <div className="card-body col">
            {openQ.length === 0 && <div className="small muted">No open questions.</div>}
            {openQ.map((q) => (
              <div key={q.id} className="claim">
                <div className="row-wrap"><Badge tone={Q_KIND[q.kind]?.tone}>{Q_KIND[q.kind]?.label || q.kind}</Badge><LabelBadge label={q.label} /><Badge>for {q.target === "departing" ? "Rohan" : "reviewer"}</Badge></div>
                <div className="small">{q.prompt}</div>
              </div>
            ))}
            {doneQ.length > 0 && <div className="divider" />}
            {doneQ.map((q) => (
              <div key={q.id} className="claim" style={{ opacity: q.status === "closed" ? 0.5 : 1 }}>
                <div className="row-wrap">{q.status === "answered" ? <Badge tone="teal"><CheckCircle2 size={11} /> Answered</Badge> : <Badge>No longer needed</Badge>}<Badge tone={Q_KIND[q.kind]?.tone}>{Q_KIND[q.kind]?.label}</Badge></div>
                <div className="small muted">{q.prompt}</div>
                {q.status === "answered" && <div className="quote">{[q.answer_value, q.answer].filter(Boolean).join(" — ")}</div>}
                {q.status === "answered" && <div className="tiny muted">Testimony from {q.answered_by} · {fmtTime(q.answered_at)} · awaiting/after reviewer verification in 04 Review</div>}
              </div>
            ))}
          </div>
        </section>
        <section className="col">
          <div className="card">
            <div className="card-head"><h3>Areas owned by the departing member</h3></div>
            <div className="card-body col gap-s">
              {ws.ledger.transfers.length === 0 && <div className="small muted">None outstanding.</div>}
              {ws.ledger.transfers.map((t) => (
                <div key={t.claim_id} className="spread">
                  <span className="small">{t.area}</span>
                  <button className="btn sm ghost" onClick={() => { const c = claims.get(t.claim_id); c && ws.openClaim(c); }}>{t.owner}</button>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h3>Decision & deadline timeline</h3></div>
            <div className="card-body">
              <div className="timeline">
                {ws.ledger.timeline.map((e, i) => (
                  <div key={i} className={`tl-item ${e.kind} ${e.conflict ? "conflict" : ""}`} onClick={() => { const c = claims.get(e.claim_id); c && ws.openClaim(c); }} style={{ cursor: "pointer" }}>
                    <div className="tiny muted mono">{fmtDate(e.date)} · {e.kind}{e.conflict && " · conflict"}</div>
                    <div className="small">{e.text}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function ConflictCard({ g, claims, ws }: { g: Conflict; claims: Map<string, Claim>; ws: WS }) {
  const toast = useToast();
  const members = g.claim_ids.map((id) => claims.get(id)).filter(Boolean) as Claim[];
  const act = async (c: Claim, decision: string) => {
    try {
      await api.review(c.id, decision);
      toast("ok", decision === "accept" ? `Resolved: ${g.attribute} = ${c.value}` : decision === "unresolved" ? "Kept unresolved — it will be released as an open question and dependent work stays blocked." : "Conflict reopened");
      await ws.reload();
    } catch (e: any) { toast("err", e.message); }
  };
  const stateBadge = g.state === "resolved" ? <Badge tone="teal"><Trophy size={11} /> Resolved by reviewer</Badge>
    : g.state === "kept_open" ? <Badge tone="amber"><PauseCircle size={11} /> Released as unresolved</Badge>
    : g.state === "dropped" ? <Badge>All sides rejected</Badge> : <Badge tone="red">Needs a decision</Badge>;
  return (
    <div className="conflict-card">
      <div className="card-head" style={{ borderBottomColor: "rgba(240,97,109,.2)" }}>
        <div className="row"><h3 style={{ textTransform: "capitalize" }}>{g.attribute.replace(/^(\w+): /, "$1 · ")}</h3>{stateBadge}</div>
        {g.state !== "open" && <button className="btn sm ghost" onClick={() => act(members[0], "reset")}><RotateCcw size={13} /> Reopen</button>}
      </div>
      <div className="card-body">
        <div className="vs" style={{ gridTemplateColumns: members.length === 2 ? "1fr auto 1fr" : `repeat(${members.length}, 1fr)` }}>
          {members.map((c, i) => (
            <Fragment key={c.id}>
              {i === 1 && members.length === 2 && <div className="vs-mid">VS</div>}
              <div className={`side ${g.winner === c.id ? "win" : g.state === "resolved" ? "lose" : ""}`}>
                <div className="spread">
                  <div className="val">{c.value}</div>
                  {c.origin === "testimony" && <Badge tone="pink">Testimony</Badge>}
                </div>
                <div className="row-wrap tiny muted">
                  {c.evidence.map((e) => <span key={e.id} className="row" style={{ gap: 4 }}><LabelBadge label={e.source_label} /> {e.source_name}</span>)}
                  {c.occurred_at && <span>· {fmtDate(c.occurred_at)}</span>}
                </div>
                <div className="quote conflict" style={{ cursor: "pointer" }} onClick={() => ws.openClaim(c)}>{c.evidence[0]?.quote}</div>
                {g.state === "open" && c.review_status !== "rejected" && (
                  <button className="btn sm success" onClick={() => act(c, "accept")}><CheckCircle2 size={13} /> Choose “{c.value.length > 22 ? c.value.slice(0, 21) + "…" : c.value}”</button>
                )}
                {c.review_note && g.state !== "open" && <div className="tiny muted">{c.review_note}</div>}
              </div>
            </Fragment>
          ))}
        </div>
        {g.state === "open" && (
          <div className="spread mt">
            <span className="small muted">Not sure? Ask Rohan in the gap interview, or release it honestly as unresolved.</span>
            <button className="btn sm warn" onClick={() => act(members[0], "unresolved")}><PauseCircle size={13} /> Keep unresolved</button>
          </div>
        )}
      </div>
    </div>
  );
}
