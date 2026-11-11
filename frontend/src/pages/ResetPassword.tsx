import { CircleCheck } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api } from "../api/client";
import { useSubmit } from "../components/AuthLayout";
import { AuthLayout, AuthSwitch, PasswordField, PasswordRule, SubmitButton } from "../components/auth";
import { FormAlert } from "../components/form";
import { errorMessage } from "../lib/errors";
import { t } from "../i18n";
import { Button } from "@/components/ui/button";

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
        <span className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <CircleCheck className="size-6" />
        </span>
        <Button asChild className="h-10 w-full">
          <Link to="/login">{t("Log in")}</Link>
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t("Choose a new password")} subtitle={t("At least {count} characters.", { count: MIN_PASSWORD })}>
      <form onSubmit={submit} className="grid gap-5">
        <FormAlert message={error} />
        {!linkDead && (
          <>
            <PasswordField
              id="password"
              label={t("New password")}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldErrors.password}
              hint={<PasswordRule value={password} min={MIN_PASSWORD} />}
              required
              autoFocus
            />
            <PasswordField
              id="confirm"
              label={t("Repeat new password")}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              error={fieldErrors.confirm}
              required
            />
            <SubmitButton busy={busy} busyLabel={t("Saving…")}>
              {t("Save new password")}
            </SubmitButton>
          </>
        )}
      </form>
      <AuthSwitch>
        {linkDead ? <Link to="/forgot-password">{t("Get a new reset link")}</Link> : <Link to="/login">{t("Back to log in")}</Link>}
      </AuthSwitch>
    </AuthLayout>
  );
}
