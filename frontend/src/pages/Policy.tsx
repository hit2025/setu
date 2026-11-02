import { Check, Minus, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth";
import { Shell } from "../components/Shell";
import { LabelBadge, ROLE_LABEL } from "../components/ui";

const ROLES = ["reviewer", "departing", "engineer", "coordinator"];

export function Policy() {
  const { system } = useAuth();
  return (
    <Shell crumbs={<b>Access policy</b>}>
      <h1>Access policy</h1>
      <p className="lead mt-s">
        Deny by default and enforced on the server — never by a model prompt. A claim can be read only by roles that may read <b>every</b> source supporting it,
        so combining permitted records can never widen access. The same policy applies to the handover page, search, citations and receipts.
      </p>
      <div className="card mt-l">
        <table className="tbl">
          <thead><tr><th>Source label</th><th>Meaning</th>{ROLES.map((r) => <th key={r} style={{ textAlign: "center" }}>{ROLE_LABEL[r]}</th>)}</tr></thead>
          <tbody>
            {system?.labels.map((l) => (
              <tr key={l.label}>
                <td><LabelBadge label={l.label} /></td>
                <td className="small muted">{l.desc}</td>
                {ROLES.map((r) => (
                  <td key={r} style={{ textAlign: "center" }}>
                    {l.readers.includes(r) ? <Check size={16} color="var(--teal)" /> : <Minus size={16} color="var(--muted)" />}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid g3 mt">
        {[
          ["Before extraction", "Confidential sources are never sent to extraction; secrets, emails and phone numbers are masked at upload, before any model call."],
          ["At release", "Recipient views are computed server-side from an approved, hashed snapshot. Unresolved conflicts are shown only if every side is visible."],
          ["On every citation open", "Each citation request re-checks the caller's role against the source's current label and verifies the source hash."],
        ].map(([t, d]) => (
          <div key={t} className="card card-pad">
            <div className="row"><ShieldCheck size={16} color="var(--accent)" /><h3>{t}</h3></div>
            <div className="small muted mt-s">{d}</div>
          </div>
        ))}
      </div>
    </Shell>
  );
}
