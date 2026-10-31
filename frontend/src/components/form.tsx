import { AlertCircle } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** A labelled control with an optional hint, or an error in its place. */
export function FormField({
  id,
  label,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="text-xs text-muted-foreground">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

/** Input wired to FormField's hint/error for screen readers. */
export function TextField({
  id,
  label,
  hint,
  error,
  className,
  ...props
}: { id: string; label: string; hint?: string; error?: string } & ComponentProps<typeof Input>) {
  return (
    <FormField id={id} label={label} hint={hint} error={error} className={className}>
      <Input
        id={id}
        name={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        {...props}
      />
    </FormField>
  );
}

/** Errors for the whole form (not tied to one field). */
export function FormAlert({ message, className }: { message: string | null | undefined; className?: string }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive",
        className,
      )}
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

/**
 * Radix Select can't hold an empty value, so "" (meaning "any") travels as a placeholder token.
 * Callers keep using "" in their own state.
 */
const EMPTY = "__any__";

export function SimpleSelect({
  id,
  value,
  onChange,
  options,
  className,
  ariaLabel,
}: {
  id?: string;
  value: string;
  onChange(value: string): void;
  options: { value: string; label: string }[];
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <Select value={value === "" ? EMPTY : value} onValueChange={(v) => onChange(v === EMPTY ? "" : v)}>
      <SelectTrigger id={id} className={cn("w-full", className)} aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value || EMPTY} value={o.value === "" ? EMPTY : o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
