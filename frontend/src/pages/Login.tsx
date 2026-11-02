import { useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2, FileSearch, GitMerge, Lock, ShieldCheck, Upload, UserCheck } from "lucide-react";
import { useAuth } from "../auth";
import { Avatar, Badge, ROLE_LABEL, useToast } from "../components/ui";
import { Logo } from "../components/Logo";

const PERSONAS = [
  { id: "dev", name: "Dev Malhotra", role: "reviewer", blurb: "Imports authorised sources, reviews every claim, resolves conflicts and approves the version that gets released.", start: "Start here" },
  { id: "rohan", name: "Rohan Das", role: "departing", blurb: "Leaving mid-release. Answers a short list of targeted gap questions instead of writing a 5-hour handover doc." },
  { id: "meera", name: "Meera Iyer", role: "engineer", blurb: "Takes over the backend. Gets verified decisions, blockers, owners and the first safe action — with citations." },
  { id: "ananya", name: "Ananya Sen", role: "coordinator", blurb: "Takes over coordination. Sees deadlines and responsibilities only — no engineering, finance or HR content." },
];

const FLOW = [
  { n: "01", t: "Connect", d: "Authorised notes, task & chat exports. Hashed, labelled, secrets masked.", icon: Upload },
  { n: "02", t: "Reconstruct", d: "Typed claims with exact character-span evidence.", icon: FileSearch },
  { n: "03", t: "Verify", d: "Anchors checked, conflicts kept visible, gaps become questions.", icon: GitMerge },
  { n: "04", t: "Review", d: "Human accepts, edits or rejects. Immutable approved version.", icon: UserCheck },
  { n: "05", t: "Handover", d: "Server-filtered view per role. Ranked actions. Receipt.", icon: Lock },
];

export function Login() {
  const { signIn, system } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const go = async (id: string) => {
    try { await signIn(id); nav("/"); } catch (e: any) { toast("err", e.message); }
  };
  return (
    <div className="login">
      <div className="login-inner fade">
        <div className="row" style={{ gap: 12 }}>
          <Logo size={44} />
          <div>
            <div className="brand-name" style={{ fontSize: 18 }}>SETU</div>
            <div className="brand-sub">by Team KavachX</div>
          </div>
        </div>
        <h1 style={{ fontSize: 42, lineHeight: 1.1, marginTop: 34, maxWidth: 860, letterSpacing: "-0.03em" }}>
          When someone leaves, <span className="grad-text">hand over the next safe action</span> — not a pile of documents.
        </h1>
        <p className="lead mt">
          SETU turns scattered project activity into an evidence-linked, reviewer-approved and permission-filtered handover.
          AI proposes claims. Deterministic code checks them. A human approves what each successor may see.
        </p>
        <div className="row-wrap mt">
          <Badge tone="teal"><CheckCircle2 size={12} /> Exact source anchors</Badge>
          <Badge tone="red">Conflicts never auto-resolved</Badge>
          <Badge tone="accent"><ShieldCheck size={12} /> Server-enforced role views</Badge>
          <Badge tone="amber">Blocked actions, not polished guesses</Badge>
          {system && <Badge tone="blue">{system.extractor.label}</Badge>}
        </div>

        <div className="card mt-l flow">
          {FLOW.map((f) => (
            <div key={f.n} className="flow-step">
              <div className="row"><f.icon size={16} color="var(--accent)" /><span className="mono tiny muted">{f.n}</span><b>{f.t}</b></div>
              <div className="small muted mt-s">{f.d}</div>
            </div>
          ))}
        </div>

        <div className="spread mt-l mb">
          <h2>Choose a persona to explore the CampusConnect handover</h2>
          <span className="small muted">No password needed — you can switch any time from the sidebar.</span>
        </div>
        <div className="grid g4">
          {PERSONAS.map((p) => (
            <button key={p.id} className="card persona" onClick={() => go(p.id)}>
              <div className="spread">
                <Avatar name={p.name} role={p.role} />
                {p.start && <Badge tone="accent">{p.start}</Badge>}
              </div>
              <div>
                <div className="strong" style={{ fontSize: 15 }}>{p.name}</div>
                <div className="small muted">{ROLE_LABEL[p.role]}</div>
              </div>
              <div className="small" style={{ color: "var(--text-2)" }}>{p.blurb}</div>
              <div className="row small strong" style={{ color: "#b3a9ff", marginTop: "auto" }}>Continue <ArrowRight size={14} /></div>
            </button>
          ))}
        </div>
        <p className="small muted mt-l">
          Demo data is synthetic (CampusConnect, a college event-registration project). It contains planted contradictions, missing owners,
          an undocumented workaround, a leaked database URL and finance/HR files — so you can watch every safeguard work.
        </p>
      </div>
    </div>
  );
}
