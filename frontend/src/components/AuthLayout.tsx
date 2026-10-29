import { useState, type FormEvent, type ReactNode } from "react";
import { Wordmark, ZellijField } from "./Zellij";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth__brand">
        <ZellijField className="auth__field" />
        <Wordmark light />
        <div className="auth__pitch">
          <p className="auth__headline">Know where every dirham goes.</p>
          <p className="auth__lede">
            Budgets, expenses and tasks for each project, with an assistant that checks the numbers before it advises.
          </p>
        </div>
      </aside>
      <main className="auth__main">
        <div className="auth__mobile-brand">
          <Wordmark />
        </div>
        <div className="auth__panel">
          <h1 className="auth__title">{title}</h1>
          <p className="auth__subtitle">{subtitle}</p>
          {children}
        </div>
      </main>
    </div>
  );
}

interface FieldProps {
  label: string;
  name: string;
  type?: string;
  autoComplete?: string;
  value: string;
  onChange(value: string): void;
  error?: string;
  hint?: string;
  required?: boolean;
  inputMode?: "text" | "decimal" | "numeric" | "email";
  maxLength?: number;
}

export function Field({
  label,
  name,
  type = "text",
  autoComplete,
  value,
  onChange,
  error,
  hint,
  required = true,
  inputMode,
  maxLength,
}: FieldProps) {
  const [shown, setShown] = useState(false);
  const isPassword = type === "password";
  const describedBy = error ? `${name}-error` : hint ? `${name}-hint` : undefined;
  return (
    <div className={error ? "field field--error" : "field"}>
      <label htmlFor={name}>{label}</label>
      <div className="field__control">
        <input
          id={name}
          name={name}
          type={isPassword && shown ? "text" : type}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          inputMode={inputMode}
          maxLength={maxLength}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
        />
        {isPassword && (
          <button type="button" className="field__toggle" onClick={() => setShown((s) => !s)} aria-pressed={shown}>
            {shown ? "Hide" : "Show"}
          </button>
        )}
      </div>
      {error ? (
        <p id={`${name}-error`} className="field__message field__message--error">
          {error}
        </p>
      ) : hint ? (
        <p id={`${name}-hint`} className="field__message">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      {message}
    </div>
  );
}

export function useSubmit(action: () => Promise<void>, onError: (e: unknown) => void) {
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await action();
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  };
  return { busy, submit };
}
