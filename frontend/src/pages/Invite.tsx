import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import type { InvitationPreview, Organization } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { Loader2, ShieldCheck } from "lucide-react";
import { AuthLayout, AuthSwitch, Notice } from "../components/auth";
import { FormAlert } from "../components/form";
import { Button } from "@/components/ui/button";
import { errorMessage } from "../lib/errors";
import { ROLE_HINT, ROLE_LABEL } from "../lib/format";
import { t } from "../i18n";

const CLOSED: Record<string, string> = {
  expired: t("This invite has expired. Ask the person who invited you for a new link."),
  revoked: t("This invite was cancelled. Ask the person who invited you for a new link."),
  accepted: t("This invite has already been used."),
};

export default function Invite() {
  const { token = "" } = useParams();
  const { user, loading, logout } = useAuth();
  const { add } = useOrg();
  const navigate = useNavigate();
  const [invite, setInvite] = useState<InvitationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ invitation: InvitationPreview }>(`/invitations/${encodeURIComponent(token)}`)
      .then((r) => setInvite(r.invitation))
      .catch((e) =>
        setError(e instanceof ApiError && e.status === 404 ? t("This invite link isn't valid.") : errorMessage(e)),
      );
  }, [token]);

  const accept = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ organization: Organization }>(`/invitations/${encodeURIComponent(token)}/accept`, {
        method: "POST",
      });
      add(r.organization);
      navigate("/app", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  const here = `/invite/${token}`;
  const title = invite ? t("Join {organization}", { organization: invite.organization_name }) : t("Invitation");
  const subtitle = invite
    ? t("{person} invited {email} as {role}.", {
        person: invite.invited_by ?? t("Someone"),
        email: invite.email,
        role: ROLE_LABEL[invite.role].toLowerCase(),
      })
    : t("Checking your invite link…");

  return (
    <AuthLayout title={title} subtitle={subtitle}>
      <div className="grid gap-5">
        <FormAlert message={error} />

        {!invite && !error && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" />
            {t("Loading…")}
          </div>
        )}

        {invite && invite.state !== "pending" && <Notice>{CLOSED[invite.state]}</Notice>}

        {invite && invite.state === "pending" && !loading && (
          <>
            <div className="flex items-start gap-3 rounded-xl border bg-muted/40 p-4">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ShieldCheck className="size-4" />
              </span>
              <span className="grid gap-0.5">
                <span className="text-sm font-medium">{ROLE_LABEL[invite.role]}</span>
                <span className="text-sm text-muted-foreground">{ROLE_HINT[invite.role]}.</span>
              </span>
            </div>

            {!user && (
              <>
                <Button asChild className="h-10 w-full">
                  <Link to={`/signup?next=${encodeURIComponent(here)}&email=${encodeURIComponent(invite.email)}`}>
                    {t("Create an account")}
                  </Link>
                </Button>
                <AuthSwitch>
                  {t("Already have an account?")} <Link to={`/login?next=${encodeURIComponent(here)}`}>{t("Log in")}</Link>
                </AuthSwitch>
              </>
            )}

            {user && user.email.toLowerCase() === invite.email && (
              <Button type="button" className="h-10 w-full" onClick={accept} disabled={busy}>
                {busy && <Loader2 className="size-4 animate-spin" />}
                {busy ? t("Joining…") : t("Join {organization}", { organization: invite.organization_name })}
              </Button>
            )}

            {user && user.email.toLowerCase() !== invite.email && (
              <>
                <Notice>
                  {t("You're logged in as {email}, but this invite is for {invited}.", {
                    email: user.email,
                    invited: invite.email,
                  })}
                </Notice>
                <Button type="button" variant="outline" className="h-10 w-full" onClick={logout}>
                  {t("Log out and switch account")}
                </Button>
              </>
            )}
          </>
        )}

        {(error || (invite && invite.state !== "pending")) && (
          <AuthSwitch>
            <Link to={user ? "/app" : "/login"}>{user ? t("Go to your dashboard") : t("Go to log in")}</Link>
          </AuthSwitch>
        )}
      </div>
    </AuthLayout>
  );
}
