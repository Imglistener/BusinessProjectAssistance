import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api, tokenStore } from "../api/client";

export interface User {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
}

interface AuthResponse {
  access_token: string;
  user: User;
}

interface AuthState {
  user: User | null;
  /** True until the stored token (if any) has been checked. */
  loading: boolean;
  login(email: string, password: string): Promise<void>;
  register(input: { first_name: string; last_name: string; email: string; password: string }): Promise<void>;
  logout(): void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => tokenStore.get() !== null);

  useEffect(() => {
    if (!tokenStore.get()) return;
    api<{ user: User }>("/auth/me")
      .then((r) => setUser(r.user))
      .catch((e) => {
        // Only drop the token when the server rejected it, not on a network blip.
        if (e instanceof ApiError && e.status === 401) tokenStore.clear();
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<AuthResponse>("/auth/login", { body: { email, password } });
    tokenStore.set(r.access_token);
    setUser(r.user);
  }, []);

  const register = useCallback<AuthState["register"]>(async (input) => {
    const r = await api<AuthResponse>("/auth/register", { body: input });
    tokenStore.set(r.access_token);
    setUser(r.user);
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
