import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { AuthLayout, Field, FormError, useSubmit } from "../components/AuthLayout";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      const r = await api<{ message: string }>("/auth/password-reset", { body: { email: email.trim() } });
      setSent(r.message);
    },
    (e) => setError(errorMessage(e)),
  );

  return (
    <AuthLayout title={t("Reset your password")} subtitle={t("We'll email you a link to choose a new one.")}>
      {sent ? (
        <div className="form">
          <p className="notice" role="status">
            {sent}
          </p>
          <p className="muted">{t("The link expires in 30 minutes. Check your spam folder if it doesn't arrive.")}</p>
        </div>
      ) : (
        <form onSubmit={submit} className="form">
          <FormError message={error} />
          <Field label={t("Email")} name="email" type="email" autoComplete="email" value={email} onChange={setEmail} />
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? t("Sending…") : t("Send reset link")}
          </button>
        </form>
      )}
      <p className="auth__switch">
        {t("Remembered it?")}{" "}<Link to="/login">{t("Log in")}
      </Link>
      </p>
    </AuthLayout>
  );
}
