import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useSubmit } from "../components/AuthLayout";
import { AuthLayout, AuthSwitch, PasswordField, PasswordRule, SubmitButton } from "../components/auth";
import { FormAlert, TextField } from "../components/form";
import { safeNext } from "../lib/format";
import { t } from "../i18n";

const MIN_PASSWORD = 8;

export default function Signup() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const invited = next.startsWith("/invite/");
  const [form, setForm] = useState({ first_name: "", last_name: "", email: params.get("email") ?? "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      setFieldErrors({});
      if (form.password.length < MIN_PASSWORD) {
        setFieldErrors({ password: t("Use at least {count} characters.", { count: MIN_PASSWORD }) });
        return;
      }
      await register({ ...form, email: form.email.trim() });
      navigate(next, { replace: true });
    },
    (e) => {
      if (e instanceof ApiError && e.code === "email_taken") {
        setFieldErrors({ email: t("An account with this email already exists. Log in instead.") });
      } else if (e instanceof ApiError && e.field) {
        setFieldErrors({ [e.field]: e.message });
      } else {
        setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again."));
      }
    },
  );

  if (user) return <Navigate to={next} replace />;

  return (
    <AuthLayout
      title={t("Create your account")}
      subtitle={invited ? t("Then you can accept your invite.") : t("You'll set up your organization next.")}
    >
      <form onSubmit={submit} className="grid gap-5">
        <FormAlert message={error} />
        <div className="grid gap-5 sm:grid-cols-2">
          <TextField
            id="first_name"
            label={t("First name")}
            autoComplete="given-name"
            value={form.first_name}
            onChange={(e) => set("first_name")(e.target.value)}
            error={fieldErrors.first_name}
            required
            maxLength={100}
            autoFocus
          />
          <TextField
            id="last_name"
            label={t("Last name")}
            autoComplete="family-name"
            value={form.last_name}
            onChange={(e) => set("last_name")(e.target.value)}
            error={fieldErrors.last_name}
            required
            maxLength={100}
          />
        </div>
        <TextField
          id="email"
          type="email"
          label={t("Email")}
          autoComplete="email"
          value={form.email}
          onChange={(e) => set("email")(e.target.value)}
          error={fieldErrors.email}
          required
          readOnly={invited && !!params.get("email")}
        />
        <PasswordField
          id="password"
          label={t("Password")}
          autoComplete="new-password"
          value={form.password}
          onChange={(e) => set("password")(e.target.value)}
          error={fieldErrors.password}
          hint={<PasswordRule value={form.password} min={MIN_PASSWORD} />}
          required
          maxLength={128}
        />
        <SubmitButton busy={busy} busyLabel={t("Creating account…")}>
          {t("Create account")}
        </SubmitButton>
      </form>
      <AuthSwitch>
        {t("Already have an account?")}{" "}
        <Link to={params.get("next") ? `/login?next=${encodeURIComponent(next)}` : "/login"}>{t("Log in")}</Link>
      </AuthSwitch>
    </AuthLayout>
  );
}
