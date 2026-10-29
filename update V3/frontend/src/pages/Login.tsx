import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthLayout, Field, FormError, useSubmit } from "../components/AuthLayout";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { busy, submit } = useSubmit(
    async () => {
      setError(null);
      await login(email.trim(), password);
      navigate("/app", { replace: true });
    },
    (e) => setError(e instanceof ApiError ? e.message : "Something went wrong. Try again."),
  );

  if (user) return <Navigate to="/app" replace />;

  return (
    <AuthLayout title="Log in" subtitle="Pick up where you left off.">
      <form onSubmit={submit} className="form">
        <FormError message={error} />
        <Field label="Email" name="email" type="email" autoComplete="email" value={email} onChange={setEmail} />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="auth__switch">
        New here? <Link to="/signup">Create an account</Link>
      </p>
    </AuthLayout>
  );
}
