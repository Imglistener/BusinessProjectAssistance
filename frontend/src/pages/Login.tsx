import { useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useSubmit } from "../components/AuthLayout";
import { Captcha, type CaptchaHandle } from "../components/Captcha";
import { AuthLayout, AuthSwitch, Notice, PasswordField, SubmitButton } from "../components/auth";
import { FormAlert, TextField } from "../components/form";
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
  const [captcha, setCaptcha] = useState<string | null>(null);
  const captchaBox = useRef<CaptchaHandle>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      if (captcha === null) {
        setError(t("Tick the box to confirm you're not a robot."));
        return;
      }
      await login(email.trim(), password, captcha);
      navigate(next, { replace: true });
    },
    (e) => {
      captchaBox.current?.reset(); // the solution was used; tick again
      setError(e instanceof ApiError ? e.message : t("Something went wrong. Try again."));
    },
  );

  if (user) return <Navigate to={next} replace />;

  return (
    <AuthLayout title={t("Log in")} subtitle={t("Pick up where you left off.")}>
      <form onSubmit={submit} className="grid gap-5">
        {expired && !error && <Notice>{t("Your session expired. Log in again to continue.")}</Notice>}
        <FormAlert message={error} />
        <TextField
          id="email"
          type="email"
          label={t("Email")}
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
        <PasswordField
          id="password"
          label={t("Password")}
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          aside={
            <Link to="/forgot-password" className="text-xs font-medium text-primary underline-offset-4 hover:underline">
              {t("Forgot your password?")}
            </Link>
          }
        />
        <Captcha ref={captchaBox} onChange={setCaptcha} />
        <SubmitButton busy={busy} busyLabel={t("Logging in…")}>
          {t("Log in")}
        </SubmitButton>
      </form>
      <AuthSwitch>
        {t("New here?")}{" "}
        <Link to={params.get("next") ? `/signup?next=${encodeURIComponent(next)}` : "/signup"}>{t("Create an account")}</Link>
      </AuthSwitch>
    </AuthLayout>
  );
}
