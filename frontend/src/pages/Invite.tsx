import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { InvitationPreview, Organization } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { AuthLayout, FormError } from "../components/AuthLayout";
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
      <div className="form">
        <FormError message={error} />

        {invite && invite.state !== "pending" && <p>{CLOSED[invite.state]}</p>}

        {invite && invite.state === "pending" && !loading && (
          <>
            <p className="muted">{ROLE_HINT[invite.role]}.</p>

            {!user && (
              <>
                <Link className="btn btn--primary btn--link" to={`/signup?next=${encodeURIComponent(here)}&email=${encodeURIComponent(invite.email)}`}>
                  {t("Create an account")}
                </Link>
                <p className="auth__switch">
                  {t("Already have an account?")}{" "}<Link to={`/login?next=${encodeURIComponent(here)}`}>{t("Log in")}
                </Link>
                </p>
              </>
            )}

            {user && user.email.toLowerCase() === invite.email && (
              <button type="button" className="btn btn--primary" onClick={accept} disabled={busy}>
                {busy ? t("Joining…") : t("Join {organization}", { organization: invite.organization_name })}
              </button>
            )}

            {user && user.email.toLowerCase() !== invite.email && (
              <>
                <p>
                  {t("You're logged in as {email}, but this invite is for {invited}.", {
                    email: user.email,
                    invited: invite.email,
                  })}
                </p>
                <button type="button" className="btn btn--primary" onClick={logout}>
                  {t("Log out and switch account")}
                </button>
              </>
            )}
          </>
        )}

        {(error || (invite && invite.state !== "pending")) && (
          <p className="auth__switch">
            <Link to={user ? "/app" : "/login"}>{user ? t("Go to your dashboard") : t("Go to log in")}</Link>
          </p>
        )}
      </div>
    </AuthLayout>
  );
}
