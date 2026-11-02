import { useMemo, useState } from "react";
import { CheckCheck, GitCompareArrows } from "lucide-react";
import { api } from "../../api";
import { ClaimCard } from "../../components/ClaimCard";
import { Empty, Spinner, useToast } from "../../components/ui";
import type { Claim } from "../../types";
import type { WS } from "../Workspace";

const FILTERS = [
  { id: "pending", label: "Needs decision" },
  { id: "testimony", label: "Testimony" },
  { id: "weak", label: "Weak support" },
  { id: "accepted", label: "Verified" },
  { id: "rejected", label: "Rejected" },
  { id: "all", label: "All" },
];

export function ReviewTab({ ws }: { ws: WS }) {
  const [f, setF] = useState("pending");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const claims = ws.ledger?.claims ?? [];
  const eligible = claims.filter((c) => c.review_status === "pending" && !c.conflict_group && c.origin !== "testimony" && c.support === "supported" && c.anchored).length;
  const reviewed = claims.filter((c) => c.review_status !== "pending").length;
  const match = (c: Claim) => f === "all" ? true : f === "pending" ? c.review_status === "pending"
    : f === "testimony" ? c.origin === "testimony" : f === "weak" ? c.support !== "supported"
    : f === "accepted" ? ["accepted", "edited", "unresolved"].includes(c.review_status) : c.review_status === f;
  const shown = useMemo(() => {
    const list = claims.filter(match);
    // Testimony first, then conflicts, then the rest.
    return list.sort((a, b) => Number(b.origin === "testimony") - Number(a.origin === "testimony") || Number(!!b.conflict_group) - Number(!!a.conflict_group));
  }, [claims, f]);

  const review = async (c: Claim, d: string, v?: string) => {
    try {
      const r = await api.review(c.id, d, v);
      if (d === "edit" && r.claim.support !== "supported") toast("info", "Edit saved, but the new value is not found in the cited evidence — it will be labelled “reviewer-asserted”.");
      await ws.reload();
    } catch (e: any) { toast("err", e.message); }
  };
  const bulk = async () => {
    setBusy(true);
    try { const r = await api.bulkAccept(ws.caseData.id); toast("ok", `${r.accepted} fully supported claims accepted`); await ws.reload(); }
    catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  };
  if (!claims.length) return <div className="card"><Empty title="Nothing to review yet">Run reconstruction first.</Empty></div>;

  return (
    <div className="col gap-l">
      <div className="card card-pad">
        <div className="spread">
          <div className="flex1">
            <h2>Claim-level review</h2>
            <div className="small muted mt-s">Accept, correct or reject each claim. Edits are re-checked against the cited evidence. Testimony from the departing member must be verified here before it can be released.</div>
            <div className="row mt">
              <div className="progress flex1" style={{ maxWidth: 420 }}><div style={{ width: `${(reviewed / claims.length) * 100}%` }} /></div>
              <span className="small mono">{reviewed}/{claims.length} decided</span>
            </div>
          </div>
          <button className="btn primary" disabled={!eligible || busy} onClick={bulk} title="Only claims with an exact anchor, full lexical support, no conflict and not testimony">
            {busy ? <Spinner /> : <CheckCheck size={15} />} Accept {eligible} fully-supported
          </button>
        </div>
      </div>
      <div className="row-wrap">
        {FILTERS.map((x) => {
          const n = claims.filter((c) => { const keep = f; return (x.id === "all" ? true : x.id === "pending" ? c.review_status === "pending" : x.id === "testimony" ? c.origin === "testimony" : x.id === "weak" ? c.support !== "supported" : x.id === "accepted" ? ["accepted", "edited", "unresolved"].includes(c.review_status) : c.review_status === x.id) && !!keep; }).length;
          return <button key={x.id} className={`btn sm ${f === x.id ? "primary" : ""}`} onClick={() => setF(x.id)}>{x.label} <span className="muted">{n}</span></button>;
        })}
      </div>
      <div className="col">
        {shown.length === 0 && <div className="card"><Empty title="Nothing here" /></div>}
        {shown.map((c) => (
          <div key={c.id}>
            {c.conflict_group && c.review_status === "pending" && (
              <div className="row small" style={{ color: "#ff9aa3", margin: "0 0 4px 4px" }}>
                <GitCompareArrows size={13} /> Part of a conflict —
                <button className="btn sm ghost" onClick={() => ws.go("verify")} style={{ height: 22 }}>resolve side by side in 03 Verify</button>
              </div>
            )}
            <ClaimCard c={c} onOpen={ws.openClaim} onReview={review} />
          </div>
        ))}
      </div>
    </div>
  );
}
