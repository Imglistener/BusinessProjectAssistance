import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout, Field, FormError, useSubmit } from "../components/AuthLayout";
import { safeNext } from "../lib/format";

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
        setFieldErrors({ password: `Use at least ${MIN_PASSWORD} characters.` });
        return;
      }
      await register({ ...form, email: form.email.trim() });
      navigate(next, { replace: true });
    },
    (e) => {
      if (e instanceof ApiError && e.code === "email_taken") {
        setFieldErrors({ email: "An account with this email already exists. Log in instead." });
      } else if (e instanceof ApiError && e.field) {
        setFieldErrors({ [e.field]: e.message });
      } else {
        setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      }
    },
  );

  if (user) return <Navigate to={next} replace />;

  return (
    <AuthLayout title="Create your account" subtitle={invited ? "Then you can accept your invite." : "You'll set up your organization next."}>
      <form onSubmit={submit} className="form">
        <FormError message={error} />
        <div className="form__row">
          <Field
            label="First name"
            name="first_name"
            autoComplete="given-name"
            value={form.first_name}
            onChange={set("first_name")}
            error={fieldErrors.first_name}
          />
          <Field
            label="Last name"
            name="last_name"
            autoComplete="family-name"
            value={form.last_name}
            onChange={set("last_name")}
            error={fieldErrors.last_name}
          />
        </div>
        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={set("email")}
          error={fieldErrors.email}
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={set("password")}
          error={fieldErrors.password}
          hint={`At least ${MIN_PASSWORD} characters.`}
        />
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="auth__switch">
        Already have an account? <Link to={params.get("next") ? `/login?next=${encodeURIComponent(next)}` : "/login"}>Log in</Link>
      </p>
    </AuthLayout>
  );
}
