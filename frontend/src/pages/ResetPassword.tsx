import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { AuthLayout, Field, FormError, useSubmit } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";

const MIN_PASSWORD = 8;

export default function ResetPassword() {
  const { token = "" } = useParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirm?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [linkDead, setLinkDead] = useState(false);
  const [done, setDone] = useState(false);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      if (password.length < MIN_PASSWORD) {
        setFieldErrors({ password: t("Use at least {count} characters.", { count: MIN_PASSWORD }) });
        return;
      }
      if (password !== confirm) {
        setFieldErrors({ confirm: t("The passwords don't match.") });
        return;
      }
      await api("/auth/password-reset/confirm", { body: { token, password } });
      setDone(true);
    },
    (e) => {
      if (e instanceof ApiError && e.code === "reset_link_invalid") setLinkDead(true);
      if (e instanceof ApiError && e.field === "password") setFieldErrors({ password: e.message });
      else setError(errorMessage(e));
    },
  );

  if (done) {
    return (
      <AuthLayout title={t("Password changed")} subtitle={t("You can log in with your new password now.")}>
        <Link className="btn btn--primary btn--link" to="/login">
          {t("Log in")}
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t("Choose a new password")} subtitle={t("At least {count} characters.", { count: MIN_PASSWORD })}>
      <form onSubmit={submit} className="form">
        <FormError message={error} />
        {!linkDead && (
          <>
            <Field
              label={t("New password")}
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={setPassword}
              error={fieldErrors.password}
            />
            <Field
              label={t("Repeat new password")}
              name="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={setConfirm}
              error={fieldErrors.confirm}
            />
            <button className="btn btn--primary" type="submit" disabled={busy}>
              {busy ? t("Saving…") : t("Save new password")}
            </button>
          </>
        )}
      </form>
      <p className="auth__switch">
        {linkDead ? <Link to="/forgot-password">{t("Get a new reset link")}</Link> : <Link to="/login">{t("Back to log in")}</Link>}
      </p>
    </AuthLayout>
  );
}
