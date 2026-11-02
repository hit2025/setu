import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { BookOpenCheck, Cpu, FolderKanban, Inbox, LogOut, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth";
import { Avatar, Badge, ROLE_LABEL, useToast } from "./ui";
import { Logo } from "./Logo";

const PERSONAS = [
  { id: "dev", name: "Dev Malhotra", role: "reviewer" },
  { id: "rohan", name: "Rohan Das", role: "departing" },
  { id: "meera", name: "Meera Iyer", role: "engineer" },
  { id: "ananya", name: "Ananya Sen", role: "coordinator" },
];

export function useSwitchPersona() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  return async (id: string) => {
    const u = await signIn(id);
    const m = loc.pathname.match(/\/(?:cases|handover)\/([a-z0-9]+)/);
    if (m) nav(u.role === "engineer" || u.role === "coordinator" ? `/handover/${m[1]}` : `/cases/${m[1]}`);
    else nav("/");
    toast("info", `Now signed in as ${u.name} (${ROLE_LABEL[u.role]})`);
  };
}

export function Shell({ crumbs, actions, children }: { crumbs?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  const { user, signOut, system } = useAuth();
  const loc = useLocation();
  const switchTo = useSwitchPersona();
  if (!user) return null;
  const home = user.role === "reviewer" ? "Handover cases" : user.role === "departing" ? "My handover interview" : "My handovers";
  const HomeIcon = user.role === "reviewer" ? FolderKanban : user.role === "departing" ? Inbox : BookOpenCheck;

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <Logo />
          <div>
            <div className="brand-name">SETU</div>
            <div className="brand-sub">by KavachX</div>
          </div>
        </Link>
        <div className="nav-label">Workspace</div>
        <Link to="/" className={`nav-item ${loc.pathname === "/" || loc.pathname.startsWith("/cases") || loc.pathname.startsWith("/handover") ? "active" : ""}`}>
          <HomeIcon size={17} /> {home}
        </Link>
        <Link to="/policy" className={`nav-item ${loc.pathname === "/policy" ? "active" : ""}`}><ShieldCheck size={17} /> Access policy</Link>

        <div className="sidebar-foot">
          <div className="card" style={{ padding: 12 }}>
            <div className="tiny muted" style={{ textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>Switch persona</div>
            <div className="col gap-s">
              {PERSONAS.map((p) => (
                <button key={p.id} className={`nav-item ${p.id === user.id ? "active" : ""}`} style={{ padding: "6px 8px" }}
                  onClick={() => p.id !== user.id && switchTo(p.id)} title={ROLE_LABEL[p.role]}>
                  <Avatar name={p.name} role={p.role} sm />
                  <div className="flex1" style={{ lineHeight: 1.2 }}>
                    <div className="small strong">{p.name}</div>
                    <div className="tiny muted">{ROLE_LABEL[p.role]}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
          <button className="nav-item" onClick={signOut}><LogOut size={16} /> Sign out</button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs">{crumbs}</div>
          <div className="row">
            {actions}
            {system && (
              <span className="hide-sm"><Badge tone={system.extractor.mode === "llm" ? "accent" : "blue"} title="Claim extraction engine">
                <Cpu size={12} /> {system.extractor.mode === "llm" ? "Claude extraction" : "Offline rule extraction"}
              </Badge></span>
            )}
            <div className="row" style={{ gap: 8 }}>
              <Avatar name={user.name} role={user.role} sm />
              <div style={{ lineHeight: 1.15 }}>
                <div className="small strong">{user.name}</div>
                <div className="tiny muted">{ROLE_LABEL[user.role]}</div>
              </div>
            </div>
          </div>
        </header>
        <main className="content fade">{children}</main>
      </div>
    </div>
  );
}
