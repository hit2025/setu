import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { SystemInfo, User } from "./types";

interface AuthCtx {
  user: User | null;
  ready: boolean;
  system: SystemInfo | null;
  signIn: (id: string) => Promise<User>;
  signOut: () => void;
}
const Ctx = createContext<AuthCtx>(null as any);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [system, setSystem] = useState<SystemInfo | null>(null);

  useEffect(() => {
    api.system().then(setSystem).catch(() => {});
    if (!getToken()) { setReady(true); return; }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
    const onLogout = () => setUser(null);
    window.addEventListener("setu:logout", onLogout);
    return () => window.removeEventListener("setu:logout", onLogout);
  }, []);

  const signIn = useCallback(async (id: string) => {
    const r = await api.login(id);
    setToken(r.token);
    setUser(r.user);
    return r.user;
  }, []);
  const signOut = useCallback(() => { setToken(null); setUser(null); }, []);

  return <Ctx.Provider value={{ user, ready, system, signIn, signOut }}>{children}</Ctx.Provider>;
}
