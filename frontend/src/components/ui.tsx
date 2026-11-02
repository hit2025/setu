import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { Claim } from "../types";

/* ---------------- toasts ---------------- */
type Toast = { id: number; kind: "ok" | "err" | "info"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === "err" ? 7000 : 3800);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === "ok" ? <CheckCircle2 size={17} color="var(--teal)" /> : t.kind === "err" ? <AlertTriangle size={17} color="var(--red)" /> : <Info size={17} color="var(--blue)" />}
            <div className="flex1">{t.text}</div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------------- primitives ---------------- */
export function Badge({ tone = "", children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} />;
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <div className="strong" style={{ color: "var(--text-2)" }}>{title}</div>
      {children && <div className="small mt-s">{children}</div>}
    </div>
  );
}

export function Stat({ label, value, tone, icon }: { label: string; value: ReactNode; tone?: string; icon?: ReactNode }) {
  return (
    <div className="card stat">
      <div className="spread">
        <div className="stat-l">{label}</div>
        {icon}
      </div>
      <div className="stat-v" style={tone ? { color: `var(--${tone})` } : undefined}>{value}</div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="drawer" style={wide ? { width: "min(860px, 100vw)" } : undefined} role="dialog" aria-modal="true">
        <div className="drawer-head">
          <div className="flex1">{title}</div>
          <button className="btn ghost icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>,
    document.body,
  );
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  if (!open) return null;
  return createPortal(
    <>
      <div className="overlay over-drawer" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true">
        <div className="card-head"><h3>{title}</h3><button className="btn ghost icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        <div className="card-body">{children}</div>
      </div>
    </>,
    document.body,
  );
}

const AV_COLORS: Record<string, string> = {
  reviewer: "linear-gradient(135deg,#b3a9ff,#8b7bff)", departing: "linear-gradient(135deg,#ffd28a,#f5b544)",
  engineer: "linear-gradient(135deg,#7ef0dd,#2dd4bf)", coordinator: "linear-gradient(135deg,#f9a8d4,#f472b6)",
};
export function Avatar({ name, role, sm }: { name: string; role: string; sm?: boolean }) {
  const initials = name.split(" ").map((p) => p[0]).slice(0, 2).join("");
  return <div className={`avatar ${sm ? "sm" : ""}`} style={{ background: AV_COLORS[role] || "#999" }}>{initials}</div>;
}

/* ---------------- domain helpers ---------------- */
export const ROLE_LABEL: Record<string, string> = {
  reviewer: "Project reviewer", departing: "Departing lead", engineer: "Incoming engineer", coordinator: "Incoming coordinator",
};

const LABEL_TONE: Record<string, string> = { public: "", team: "blue", engineering: "accent", finance: "amber", confidential: "red", testimony: "pink" };
export function LabelBadge({ label }: { label: string }) {
  return <Badge tone={LABEL_TONE[label] || ""}><span className="dot" />{label}</Badge>;
}

export const TYPE_TONE: Record<string, string> = {
  decision: "accent", owner: "teal", task: "blue", deadline: "amber", dependency: "", risk: "red", contact: "pink", status: "", note: "pink",
};

export function claimState(c: Claim): { label: string; tone: string } {
  if (c.review_status === "rejected") return { label: "Rejected", tone: "" };
  if (c.review_status === "unresolved") return { label: "Released as unresolved", tone: "amber" };
  if (c.review_status === "accepted" || c.review_status === "edited") {
    if (c.review_status === "edited" && c.support !== "supported") return { label: "Reviewer-asserted", tone: "amber" };
    return { label: c.review_status === "edited" ? "Verified · edited" : "Verified", tone: "teal" };
  }
  if (c.conflict_group) return { label: "Conflict", tone: "red" };
  if (c.origin === "testimony") return { label: "Testimony · unverified", tone: "pink" };
  if (!c.anchored) return { label: "Invalid anchor", tone: "red" };
  if (c.support === "supported") return { label: "Supported · unreviewed", tone: "blue" };
  return { label: c.support === "weak" ? "Weak support" : "Unsupported", tone: "amber" };
}

export function ClaimStateBadge({ c }: { c: Claim }) {
  const s = claimState(c);
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export const READINESS: Record<string, { label: string; tone: string }> = {
  ready: { label: "Ready", tone: "teal" },
  reassign: { label: "Owner leaving", tone: "amber" },
  needs_owner: { label: "Needs owner", tone: "amber" },
  blocked: { label: "Blocked", tone: "red" },
  done: { label: "Done", tone: "" },
};

export function fmtDate(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s.length === 10 ? s + "T00:00:00" : s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
export function fmtTime(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
export const shortHash = (h?: string) => (h ? `${h.slice(0, 8)}…${h.slice(-4)}` : "—");
