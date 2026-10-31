import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout, Field, FormError, useSubmit } from "../components/AuthLayout";
import { safeNext } from "../lib/format";
import { t } from "../i18n";

export default function Login() {
  const { user, login, expired } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      await login(email.trim(), password);
      navigate(next, { replace: true });
    },
    (e) => setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again.")),
  );

  if (user) return <Navigate to={next} replace />;

  return (
    <AuthLayout title={t("Log in")} subtitle={t("Pick up where you left off.")}>
      <form onSubmit={submit} className="form">
        {expired && !error && (
          <p className="notice" role="status">
            {t("Your session expired. Log in again to continue.")}
          </p>
        )}
        <FormError message={error} />
        <Field label={t("Email")} name="email" type="email" autoComplete="email" value={email} onChange={setEmail} />
        <Field
          label={t("Password")}
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <Link to="/forgot-password" className="form__aside">
          {t("Forgot your password?")}
        </Link>
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? t("Logging in…") : t("Log in")}
        </button>
      </form>
      <p className="auth__switch">
        {t("New here?")}{" "}<Link to={params.get("next") ? `/signup?next=${encodeURIComponent(next)}` : "/signup"}>{t("Create an account")}
      </Link>
      </p>
    </AuthLayout>
  );
}
