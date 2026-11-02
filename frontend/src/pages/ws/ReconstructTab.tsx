import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Cpu, Play, RefreshCw } from "lucide-react";
import { useAuth } from "../../auth";
import { ClaimCard } from "../../components/ClaimCard";
import { Badge, Empty, Spinner, Stat } from "../../components/ui";
import type { WS } from "../Workspace";

const TYPES = ["decision", "owner", "task", "deadline", "dependency", "risk", "contact", "status", "note"];

export function ReconstructTab({ ws }: { ws: WS }) {
  const { system } = useAuth();
  const [type, setType] = useState("all");
  const running = ws.job && (ws.job.status === "queued" || ws.job.status === "running");
  const result = ws.job?.status === "done" ? ws.job.result : null;
  const claims = ws.ledger?.claims ?? [];
  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    claims.forEach((c) => (m[c.ctype] = (m[c.ctype] || 0) + 1));
    return m;
  }, [claims]);
  const shown = claims.filter((c) => type === "all" || c.ctype === type);

  return (
    <div className="col gap-l">
      <div className="card card-pad">
        <div className="spread">
          <div>
            <h2>Reconstruct the project state</h2>
            <div className="muted small mt-s">
              AI (or the offline rule engine) proposes typed claims; code anchors each one to an exact character span, merges corroborating sources,
              derives who may read it, and reconciles conflicts. Re-running keeps your review decisions.
            </div>
            <div className="row-wrap mt">
              <Badge tone={system?.extractor.mode === "llm" ? "accent" : "blue"}><Cpu size={12} /> {system?.extractor.label}</Badge>
              {ws.caseData.extractor_used && <Badge>Last run: {ws.caseData.extractor_used}</Badge>}
            </div>
          </div>
          <button className="btn primary lg" onClick={ws.startJob} disabled={!!running || !ws.sources.length}>
            {running ? <Spinner /> : claims.length ? <RefreshCw size={16} /> : <Play size={16} />} {claims.length ? "Re-run reconstruction" : "Run reconstruction"}
          </button>
        </div>
        {running && ws.job && (
          <div className="mt">
            <div className="spread small mb"><span>{ws.job.message}</span><span className="mono">{ws.job.progress}%</span></div>
            <div className="progress"><div style={{ width: `${ws.job.progress}%` }} /></div>
          </div>
        )}
        {ws.job?.status === "failed" && <div className="notice red mt"><AlertTriangle size={16} /> {ws.job.message}</div>}
        {result && (
          <div className="mt">
            <div className="notice teal small"><CheckCircle2 size={16} /> {result.claims} claims from {result.candidates} candidates · {result.conflicts} conflicts · {result.citations_rejected} invalid citations rejected · extractor: {result.extractors.join(", ")}</div>
            {result.excluded_sources?.length > 0 && <div className="notice small mt-s">Not extracted (confidential): {result.excluded_sources.join(", ")}</div>}
            {result.warnings?.map((w: string) => <div key={w} className="notice amber small mt-s">{w}</div>)}
          </div>
        )}
      </div>
      {claims.length > 0 ? (
        <>
          <div className="grid g4">
            <Stat label="Decisions" value={counts.decision || 0} />
            <Stat label="Tasks & owners" value={`${counts.task || 0} / ${counts.owner || 0}`} />
            <Stat label="Deadlines & dependencies" value={`${counts.deadline || 0} / ${counts.dependency || 0}`} />
            <Stat label="Risks & tacit notes" value={(counts.risk || 0) + (counts.note || 0)} />
          </div>
          <div className="card">
            <div className="card-head">
              <h3>Typed claim ledger</h3>
              <div className="row-wrap">
                <button className={`btn sm ${type === "all" ? "primary" : ""}`} onClick={() => setType("all")}>All {claims.length}</button>
                {TYPES.filter((t) => counts[t]).map((t) => (
                  <button key={t} className={`btn sm ${type === t ? "primary" : ""}`} onClick={() => setType(t)}>{t} {counts[t]}</button>
                ))}
              </div>
            </div>
            <div className="card-body col">
              {shown.map((c) => <ClaimCard key={c.id} c={c} onOpen={ws.openClaim} />)}
            </div>
          </div>
        </>
      ) : !running && (
        <div className="card"><Empty title="No claims yet">Run reconstruction to build the ledger from your {ws.sources.length} source(s).</Empty></div>
      )}
    </div>
  );
}
