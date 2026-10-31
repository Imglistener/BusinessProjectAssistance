import { MailCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useSubmit } from "../components/AuthLayout";
import { AuthLayout, AuthSwitch, SubmitButton } from "../components/auth";
import { FormAlert, TextField } from "../components/form";
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
        <div className="grid gap-3 rounded-xl border bg-muted/40 p-5" role="status">
          <span className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MailCheck className="size-5" />
          </span>
          <p className="text-sm font-medium">{sent}</p>
          <p className="text-sm text-muted-foreground">
            {t("The link expires in 30 minutes. Check your spam folder if it doesn't arrive.")}
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="grid gap-5">
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
          <SubmitButton busy={busy} busyLabel={t("Sending…")}>
            {t("Send reset link")}
          </SubmitButton>
        </form>
      )}
      <AuthSwitch>
        {t("Remembered it?")} <Link to="/login">{t("Log in")}</Link>
      </AuthSwitch>
    </AuthLayout>
  );
}
