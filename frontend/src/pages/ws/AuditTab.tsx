import { useEffect, useState } from "react";
import { api } from "../../api";
import { Badge, Spinner, fmtTime } from "../../components/ui";
import type { WS } from "../Workspace";

const TONE: Record<string, string> = {
  version_approved: "teal", handover_acknowledged: "teal", claim_accept: "teal", claim_reject: "red", claim_edit: "amber",
  claim_unresolved: "amber", question_answered: "pink", reconstruct: "accent", source_uploaded: "blue", citation_opened: "",
};

export function AuditTab({ ws }: { ws: WS }) {
  const [events, setEvents] = useState<any[] | null>(null);
  useEffect(() => { api.audit(ws.caseData.id).then(setEvents); }, [ws.caseData]);
  if (!events) return <div className="row"><Spinner /> Loading…</div>;
  return (
    <div className="card">
      <div className="card-head"><h3>Audit trail</h3><span className="small muted">Every upload, extraction, review decision, approval, citation open and receipt</span></div>
      <table className="tbl">
        <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td className="small muted" style={{ whiteSpace: "nowrap" }}>{fmtTime(e.at)}</td>
              <td className="small strong">{e.actor}</td>
              <td><Badge tone={TONE[e.action] || ""}>{e.action.replace(/_/g, " ")}</Badge></td>
              <td className="mono muted" style={{ fontSize: 11, maxWidth: 560, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={JSON.stringify(e.detail)}>{JSON.stringify(e.detail)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
