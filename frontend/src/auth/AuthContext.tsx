import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, SESSION_EXPIRED_EVENT, api, tokenStore } from "../api/client";
import { getLang } from "../i18n";

export interface User {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  /** Language for emails and notifications; follows the language picked in the app. */
  locale: string;
}

/** The language picked on this device wins; keep the account in step so emails match. */
function syncLocale(user: User) {
  if (user.locale !== getLang()) api("/auth/me", { method: "PATCH", body: { locale: getLang() } }).catch(() => undefined);
}

interface AuthResponse {
  access_token: string;
  user: User;
}

interface AuthState {
  user: User | null;
  /** True until the stored token (if any) has been checked. */
  loading: boolean;
  /** The last session ended because the login expired (not a manual log out). */
  expired: boolean;
  /** `captcha`: the solved challenge from the login form ("" when the server has the captcha off). */
  login(email: string, password: string, captcha?: string): Promise<void>;
  register(input: { first_name: string; last_name: string; email: string; password: string; captcha?: string }): Promise<void>;
  logout(): void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => tokenStore.get() !== null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setExpired(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    if (!tokenStore.get()) return;
    api<{ user: User }>("/auth/me")
      .then((r) => {
        setUser(r.user);
        syncLocale(r.user);
      })
      .catch((e) => {
        // Only drop the token when the server rejected it, not on a network blip.
        if (e instanceof ApiError && e.status === 401) tokenStore.clear();
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string, captcha?: string) => {
    const r = await api<AuthResponse>("/auth/login", { body: { email, password, captcha } });
    tokenStore.set(r.access_token);
    setUser(r.user);
    syncLocale(r.user);
    setExpired(false);
  }, []);

  const register = useCallback<AuthState["register"]>(async (input) => {
    const r = await api<AuthResponse>("/auth/register", { body: { ...input, locale: getLang() } });
    tokenStore.set(r.access_token);
    setUser(r.user);
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setExpired(false);
  }, []);

  const value = useMemo(
    () => ({ user, loading, expired, login, register, logout }),
    [user, loading, expired, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
