import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokens } from "../../lib/api";
import type { User } from "../../lib/types";

interface Ctx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: Record<string, unknown>) => Promise<void>;
  logout: () => void;
}
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!tokens.get());
  const qc = useQueryClient();

  const loadMe = useCallback(async () => {
    try {
      setUser(await api.get<User>("/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tokens.get()) void loadMe();
  }, [loadMe]);
  useEffect(() => {
    const h = () => {
      setUser(null);
      qc.clear();
    };
    window.addEventListener("saturna:logout", h);
    return () => window.removeEventListener("saturna:logout", h);
  }, [qc]);

  const start = async (path: string, body: unknown) => {
    tokens.set(await api.post(path, body));
    qc.clear();
    await loadMe();
  };

  return (
    <AuthCtx.Provider
      value={{
        user,
        loading,
        login: (email, password) => start("/auth/login", { email, password }),
        register: (data) => start("/auth/register", data),
        logout: () => {
          tokens.clear();
          setUser(null);
          qc.clear();
        },
      }}
    >
      {children}
    </AuthCtx.Provider>
  );
}
