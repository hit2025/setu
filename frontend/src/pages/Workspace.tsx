import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Activity, ClipboardCheck, FileStack, GitCompareArrows, LayoutDashboard, Rocket, ScrollText, Wand2 } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { EvidenceDrawer } from "../components/Evidence";
import { Shell } from "../components/Shell";
import { Spinner, useToast } from "../components/ui";
import type { Case, Claim, Job, Ledger, Question, Source } from "../types";
import { Interview } from "./Interview";
import { AuditTab } from "./ws/AuditTab";
import { OverviewTab } from "./ws/OverviewTab";
import { ReconstructTab } from "./ws/ReconstructTab";
import { ReleaseTab } from "./ws/ReleaseTab";
import { ReviewTab } from "./ws/ReviewTab";
import { SourcesTab } from "./ws/SourcesTab";
import { VerifyTab } from "./ws/VerifyTab";

export interface WS {
  caseData: Case;
  sources: Source[];
  ledger: Ledger | null;
  questions: Question[];
  job: Job | null;
  reload: () => Promise<void>;
  startJob: () => Promise<void>;
  openClaim: (c: Claim) => void;
  go: (tab: string) => void;
}

export const STEPS = [
  { id: "sources", n: "01", t: "Connect", d: "Authorised sources" },
  { id: "reconstruct", n: "02", t: "Reconstruct", d: "Typed claim ledger" },
  { id: "verify", n: "03", t: "Verify", d: "Conflicts, gaps, readiness" },
  { id: "review", n: "04", t: "Review", d: "Accept, edit, reject" },
  { id: "release", n: "05", t: "Handover", d: "Approve & release" },
];

export function Workspace() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "overview";
  const [caseData, setCase] = useState<Case | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [claim, setClaim] = useState<Claim | null>(null);
  const [err, setErr] = useState("");
  const toast = useToast();
  const poll = useRef<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const [c, s, l, q] = await Promise.all([api.case(id), api.sources(id), api.ledger(id), api.questions(id)]);
      setCase(c); setSources(s); setLedger(l); setQuestions(q);
      if (c.job && (c.job.status === "queued" || c.job.status === "running")) watch(c.job.id);
    } catch (e: any) { setErr(e.message); }
  }, [id]);

  const watch = (jid: string) => {
    if (poll.current) return;
    const tick = async () => {
      try {
        const j = await api.job(jid);
        setJob(j);
        if (j.status === "done" || j.status === "failed") {
          poll.current = null;
          if (j.status === "done") toast("ok", `Reconstruction complete: ${j.result.claims} claims, ${j.result.conflicts} conflicts`);
          else toast("err", `Reconstruction failed: ${j.message}`);
          await reload();
          return;
        }
      } catch { /* transient */ }
      poll.current = window.setTimeout(tick, 600);
    };
    poll.current = window.setTimeout(tick, 300);
  };

  useEffect(() => { reload(); return () => { if (poll.current) clearTimeout(poll.current); poll.current = null; }; }, [reload]);

  const startJob = async () => {
    try { const r = await api.reconstruct(id); setJob({ id: r.id, status: r.status, progress: 2, message: "Queued", result: {} }); watch(r.id); }
    catch (e: any) { toast("err", e.message); }
  };
  const go = (t: string) => { setSp(t === "overview" ? {} : { tab: t }); window.scrollTo({ top: 0 }); };

  if (user?.role === "departing") return <Interview />;
  if (err) return <Shell crumbs={<b>Case</b>}><div className="notice red">{err}</div></Shell>;
  if (!caseData) return <Shell crumbs={<b>Loading…</b>}><div className="row"><Spinner /> Loading workspace…</div></Shell>;

  const ws: WS = { caseData, sources, ledger, questions, job, reload, startJob, openClaim: setClaim, go };
  const open = caseData.counts;
  const tabs = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "sources", label: "01 Sources", icon: FileStack, count: open.sources },
    { id: "reconstruct", label: "02 Reconstruct", icon: Wand2 },
    { id: "verify", label: "03 Verify", icon: GitCompareArrows, count: ledger?.conflicts.filter((c) => c.state === "open").length, hot: true },
    { id: "review", label: "04 Review", icon: ClipboardCheck, count: open.pending, hot: false },
    { id: "release", label: "05 Release", icon: Rocket, count: open.versions },
    { id: "audit", label: "Audit log", icon: ScrollText },
  ];

  return (
    <Shell crumbs={<><span>Handover cases</span><span>/</span><b>{caseData.project} · {caseData.name}</b></>}
      actions={job && (job.status === "running" || job.status === "queued") ? <span className="badge accent"><Activity size={12} /> Reconstructing {job.progress}%</span> : null}>
      <div className="spread">
        <div>
          <div className="small muted">{caseData.project}</div>
          <h1>{caseData.name}</h1>
        </div>
      </div>
      <div className="stepper mt">
        {STEPS.map((s, i) => (
          <button key={s.id} className={`step ${i + 1 < caseData.stage ? "done" : i + 1 === caseData.stage ? "current" : ""}`} onClick={() => go(s.id)}>
            <div className="n">{s.n}{i + 1 < caseData.stage ? " ✓" : ""}</div>
            <div className="t">{s.t}</div>
            <div className="d">{s.d}</div>
          </button>
        ))}
      </div>
      <div className="tabs mt">
        {tabs.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => go(t.id)}>
            <t.icon size={15} /> {t.label}
            {!!t.count && <span className={`count ${t.hot ? "hot" : ""}`}>{t.count}</span>}
          </button>
        ))}
      </div>
      {tab === "overview" && <OverviewTab ws={ws} />}
      {tab === "sources" && <SourcesTab ws={ws} />}
      {tab === "reconstruct" && <ReconstructTab ws={ws} />}
      {tab === "verify" && <VerifyTab ws={ws} />}
      {tab === "review" && <ReviewTab ws={ws} />}
      {tab === "release" && <ReleaseTab ws={ws} />}
      {tab === "audit" && <AuditTab ws={ws} />}
      <EvidenceDrawer claim={claim} mode={{ kind: "workspace" }} onClose={() => setClaim(null)} />
    </Shell>
  );
}
