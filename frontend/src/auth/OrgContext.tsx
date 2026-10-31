import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Organization } from "../api/models";
import { errorMessage } from "../lib/errors";
import { useAuth } from "./AuthContext";
import { t } from "../i18n";

const ORG_KEY = "bpa.org";

interface OrgState {
  /** null while loading */
  orgs: Organization[] | null;
  /** The organization every signed-in page works in; null when the user has none. */
  org: Organization | null;
  error: string | null;
  select(id: number): void;
  /** After creating or joining one: add it and switch to it. */
  add(org: Organization): void;
  /** After leaving one. */
  remove(id: number): void;
}

const OrgContext = createContext<OrgState | null>(null);

const stored = () => {
  try {
    return Number(localStorage.getItem(ORG_KEY)) || null;
  } catch {
    return null;
  }
};

const store = (id: number) => {
  try {
    localStorage.setItem(ORG_KEY, String(id));
  } catch {
    /* storage unavailable: the choice lasts until reload */
  }
};

export function OrgProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [currentId, setCurrentId] = useState<number | null>(stored);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOrgs(null);
    setError(null);
    if (!user) return;
    api<{ organizations: Organization[] }>("/organizations")
      .then((r) => setOrgs(r.organizations))
      .catch((e) => setError(errorMessage(e, t("Couldn't load your organizations."))));
  }, [user]);

  const select = useCallback((id: number) => {
    setCurrentId(id);
    store(id);
  }, []);

  const add = useCallback(
    (org: Organization) => {
      setOrgs((prev) => [...(prev ?? []).filter((o) => o.id !== org.id), org].sort((a, b) => a.name.localeCompare(b.name)));
      select(org.id);
    },
    [select],
  );

  const remove = useCallback((id: number) => setOrgs((prev) => prev?.filter((o) => o.id !== id) ?? prev), []);

  // Fall back to the first organization when the stored one is gone (left, removed, other account).
  const org = orgs ? orgs.find((o) => o.id === currentId) ?? orgs[0] ?? null : null;

  const value = useMemo(() => ({ orgs, org, error, select, add, remove }), [orgs, org, error, select, add, remove]);
  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrg(): OrgState {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrg must be used inside <OrgProvider>");
  return ctx;
}
