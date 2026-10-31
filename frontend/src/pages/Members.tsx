import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { canManageMembers, type Invitation, type Member, type Organization, type Role } from "../api/models";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { AppShell } from "../components/AppShell";
import { Field, FormError, SelectField, useSubmit } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { ROLE_HINT, ROLE_LABEL, formatDate } from "../lib/format";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

const ASSIGNABLE: Role[] = ["owner", "project_manager", "contributor", "viewer"];
const ROLE_OPTIONS = ASSIGNABLE.map((r) => ({ value: r, label: ROLE_LABEL[r] }));

export default function Members() {
  const { orgs, org, error } = useOrg();

  return (
    <AppShell>
      <header className="main__header">
        <h1>{t("Members")}</h1>
        {org && <p className="main__org">{t("People in {organization} and what they can do.", { organization: org.name })}</p>}
      </header>
      <FormError message={error} />
      {orgs === null && !error && <p className="muted">{t("Loading…")}</p>}
      {orgs !== null && !org && (
        <p className="muted">
          {tx("Create your organization on the {dashboard} first.", { dashboard: <Link to="/app">{t("dashboard")}</Link> })}
        </p>
      )}
      {org && <MemberManager key={org.id} org={org} />}
    </AppShell>
  );
}

function MemberManager({ org }: { org: Organization }) {
  const { user } = useAuth();
  const { remove } = useOrg();
  const navigate = useNavigate();
  const isOwner = canManageMembers(org.role);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ members: Member[] }>(`/organizations/${org.id}/members`)
      .then((r) => setMembers(r.members))
      .catch((e) => setError(errorMessage(e, t("Couldn't load members."))));
    if (isOwner) {
      api<{ invitations: Invitation[] }>(`/organizations/${org.id}/invitations`)
        .then((r) => setInvitations(r.invitations))
        .catch((e) => setError(errorMessage(e, t("Couldn't load invitations."))));
    }
  }, [org.id, isOwner]);

  useEffect(load, [load]);

  const changeRole = async (m: Member, role: Role) => {
    setError(null);
    try {
      await api(`/organizations/${org.id}/members/${m.user_id}`, { method: "PATCH", body: { role } });
      if (m.user_id === user?.id) {
        // Stepping down changes what this page may show; reload everything.
        window.location.reload();
        return;
      }
      setMembers((prev) => prev?.map((x) => (x.user_id === m.user_id ? { ...x, role } : x)) ?? prev);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const removeMember = async (m: Member) => {
    setError(null);
    try {
      await api(`/organizations/${org.id}/members/${m.user_id}/remove`, { method: "POST" });
      if (m.user_id === user?.id) {
        remove(org.id);
        navigate("/app", { replace: true });
        return;
      }
      setMembers((prev) => prev?.filter((x) => x.user_id !== m.user_id) ?? prev);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      <FormError message={error} />

      {isOwner && <InviteForm org={org} onInvited={load} />}

      <section className="projects-section" aria-labelledby="members-heading">
        <div className="section-head">
          <h2 id="members-heading">{t("People")}</h2>
        </div>
        {members === null && !error && <p className="muted">{t("Loading…")}</p>}
        {members && (
          <ul className="rows">
            {members.map((m) => (
              <MemberRow
                key={m.user_id}
                member={m}
                isMe={m.user_id === user?.id}
                canManage={isOwner}
                onRoleChange={(role) => changeRole(m, role)}
                onRemove={() => removeMember(m)}
              />
            ))}
          </ul>
        )}
      </section>

      {isOwner && invitations.length > 0 && (
        <section className="projects-section" aria-labelledby="invites-heading">
          <div className="section-head">
            <h2 id="invites-heading">{t("Pending invites")}</h2>
          </div>
          <ul className="rows">
            {invitations.map((inv) => (
              <InvitationRow
                key={inv.id}
                invitation={inv}
                onRevoke={async () => {
                  setError(null);
                  try {
                    await api(`/organizations/${org.id}/invitations/${inv.id}/revoke`, { method: "POST" });
                    setInvitations((prev) => prev.filter((x) => x.id !== inv.id));
                  } catch (e) {
                    setError(errorMessage(e));
                  }
                }}
              />
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function MemberRow({
  member,
  isMe,
  canManage,
  onRoleChange,
  onRemove,
}: {
  member: Member;
  isMe: boolean;
  canManage: boolean;
  onRoleChange(role: Role): void;
  onRemove(): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const canRemove = canManage || isMe;
  const removeLabel = isMe ? t("Leave") : t("Remove");

  return (
    <li className="row">
      <div className="row__main">
        <p className="row__title">
          {member.name}
          {isMe && <span className="tag">{t("You")}</span>}
        </p>
        <p className="row__meta">{member.email ?? ROLE_HINT[member.role] ?? ROLE_LABEL[member.role]}</p>
      </div>
      <div className="row__side">
        {canManage ? (
          <select
            className="status-select"
            aria-label={t("Role for {name}", { name: member.name })}
            value={member.role}
            onChange={(e) => onRoleChange(e.target.value as Role)}
          >
            {ROLE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        ) : (
          <span>{ROLE_LABEL[member.role]}</span>
        )}
        {canRemove &&
          (confirming ? (
            <span className="row__confirm">
              <button type="button" className="link-btn link-btn--danger" onClick={onRemove}>
                {isMe ? t("Leave organization") : t("Remove {name}", { name: member.name.split(" ")[0] })}
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirming(false)}>
                {t("Cancel")}
              </button>
            </span>
          ) : (
            <button type="button" className="link-btn" onClick={() => setConfirming(true)}>
              {removeLabel}
            </button>
          ))}
      </div>
    </li>
  );
}

function InvitationRow({ invitation, onRevoke }: { invitation: Invitation; onRevoke(): void }) {
  const expired = invitation.state === "expired";
  return (
    <li className="row">
      <div className="row__main">
        <p className="row__title">
          {invitation.email}
          {expired && <span className="tag">{t("Expired")}</span>}
        </p>
        <p className="row__meta">
          {ROLE_LABEL[invitation.role]}.{" "}
          {expired ? t("Send a new invite if they still need access.") : t("Link works until {date}.", { date: formatDate(invitation.expires_at.slice(0, 10)) })}
        </p>
      </div>
      <div className="row__side">
        <button type="button" className="link-btn" onClick={onRevoke}>
          {expired ? t("Dismiss") : t("Cancel invite")}
        </button>
      </div>
    </li>
  );
}

function InviteForm({ org, onInvited }: { org: Organization; onInvited(): void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("contributor");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [link, setLink] = useState<{ email: string; url: string; emailed: boolean } | null>(null);
  const [copied, setCopied] = useState(false);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldError(undefined);
      const r = await api<{ invitation: Invitation; token: string; emailed: boolean }>(`/organizations/${org.id}/invitations`, {
        body: { email: email.trim(), role },
      });
      setLink({ email: r.invitation.email, url: `${window.location.origin}/invite/${r.token}`, emailed: r.emailed });
      setCopied(false);
      setEmail("");
      onInvited();
    },
    (e) => {
      if (e instanceof ApiError && e.field === "email") setFieldError(e.message);
      else setError(errorMessage(e));
    },
  );

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
    } catch {
      /* clipboard blocked: the link is selectable */
    }
  };

  return (
    <section className="panel" aria-labelledby="invite-heading">
      <h2 id="invite-heading" className="panel__title">
        {t("Invite someone")}
      </h2>
      <p className="muted invite__lede">
        {t("You'll get a link to send them (it's also emailed once email is set up). It works only for that email address and expires in 7 days.")}
      </p>
      <form onSubmit={submit} className="form invite__form">
        <FormError message={error} />
        <div className="form__row">
          <Field label={t("Email")} name="invite_email" type="email" value={email} onChange={setEmail} error={fieldError} />
          <SelectField label={t("Role")} name="invite_role" value={role} onChange={setRole} options={ROLE_OPTIONS} />
        </div>
        <p className="muted invite__hint">{ROLE_HINT[role]}.</p>
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={busy}>
            {busy ? t("Creating link…") : t("Create invite link")}
          </button>
        </div>
      </form>

      {link && (
        <div className="invite__link" role="status">
          <p>
            {link.emailed ? (
              <>
                {tx("We emailed the invite to {email}. You can also send this link yourself; it's shown only once.", {
                  email: <strong>{link.email}</strong>,
                })}
              </>
            ) : (
              <>
                {tx("Send this link to {email}. It's shown only once.", { email: <strong>{link.email}</strong> })}
              </>
            )}
          </p>
          <div className="invite__copy">
            <input readOnly value={link.url} aria-label={t("Invite link")} onFocus={(e) => e.target.select()} />
            <button type="button" className="btn btn--primary" onClick={copy}>
              {copied ? t("Copied") : t("Copy link")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
