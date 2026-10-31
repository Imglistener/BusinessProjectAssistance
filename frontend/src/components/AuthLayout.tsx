import { useState, type FormEvent } from "react";
import { t } from "../i18n";

// The sign-in pages use components/auth.tsx. Field, SelectField and FormError below are the older form
// helpers still used by screens that haven't been rebuilt with Tailwind yet.
export { AuthLayout } from "./auth";

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
            {shown ? t("Hide") : t("Show")}
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

interface SelectProps {
  label: string;
  name: string;
  value: string;
  onChange(value: string): void;
  options: { value: string; label: string }[];
}

export function SelectField({ label, name, value, onChange, options }: SelectProps) {
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <div className="field__control">
        <select id={name} name={name} value={value} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
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
