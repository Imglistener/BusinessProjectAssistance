import { Check, Eye, EyeOff, Info, Loader2, Plane, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";
import { useReduceMotion } from "../hooks/use-reduce-motion";
import { useState, type ComponentProps, type ReactNode } from "react";
import { Link } from "react-router-dom";
import DotGrid from "./effects/DotGrid";
import { LanguagePicker } from "./LanguagePicker";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { isRtl, t } from "../i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Frame for the signed-out pages (log in, sign up, password reset, invites): the form on one side and,
 * on wide screens, a dark panel that shows what the product does.
 */
export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-svh bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-10">
        <header className="flex items-center justify-between gap-4">
          <Link to="/" className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <Logo compact />
          </Link>
          <div className="flex items-center gap-1">
            <LanguagePicker />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex flex-1 items-center justify-center py-12">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.2, 0.7, 0.2, 1] }}
            className="grid w-full max-w-sm gap-8"
          >
            <div className="grid gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
              <p className="text-sm text-muted-foreground">{subtitle}</p>
            </div>
            {children}
          </motion.div>
        </main>
        <p className="text-center text-xs text-muted-foreground lg:text-start">
          {t("Amounts in MAD by default. Fuel prices: averages from prix-gasoil-maroc.teraedge.ma.")}
        </p>
      </div>
      <Showcase />
    </div>
  );
}

/** The dark panel: headline, a miniature of the dashboard, and the dot grid reacting to the pointer. */
function Showcase() {
  const reduce = useReduceMotion();
  return (
    <aside className="relative isolate hidden overflow-hidden bg-zinc-950 p-3 text-white lg:block">
      <div className="relative flex h-full flex-col justify-between overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/40 p-10 xl:p-14">
        <div aria-hidden="true" className="absolute inset-0 -z-10 opacity-70 [mask-image:radial-gradient(ellipse_80%_70%_at_50%_45%,#000_30%,transparent_100%)]">
          <DotGrid
            dotSize={3}
            gap={24}
            baseColor="#27272f"
            activeColor="#7c86ff"
            proximity={140}
            shockRadius={200}
            shockStrength={3}
            intro={!reduce}
            mouseInteraction={!reduce}
            paused={!!reduce}
            className="h-full w-full"
          />
        </div>
        <div aria-hidden="true" className="absolute -bottom-40 start-1/4 -z-10 size-[30rem] rounded-full bg-indigo-500/25 blur-[120px]" />

        <div className="grid max-w-md gap-4">
          <p className="text-3xl font-semibold leading-tight tracking-tight xl:text-4xl">
            {t("Know where every dirham goes.")}
          </p>
          <p className="text-base text-zinc-400">
            {t("Budgets, expenses and tasks for each project, with an assistant that checks the numbers before it advises.")}
          </p>
        </div>

        <Preview />

        <ul className="grid gap-2.5 text-sm text-zinc-300">
          {[t("It drafts, you decide."), t("It says what it assumed."), t("It only sees your organization.")].map((line) => (
            <li key={line} className="flex items-center gap-2.5">
              <span className="flex size-5 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-300">
                <Check className="size-3" />
              </span>
              {line}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

/** A small, static picture of the dashboard (decorative: the real figures are inside the app). */
function Preview() {
  const rtl = isRtl();
  return (
    <motion.div
      aria-hidden="true"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.25, ease: [0.2, 0.7, 0.2, 1] }}
      className="relative mx-auto w-full max-w-md"
    >
      <div className="rounded-xl border border-white/10 bg-zinc-900/80 p-5 shadow-2xl shadow-black/40 backdrop-blur">
        <p className="text-xs text-zinc-400">{t("Website redesign")}</p>
        <p className="tabular mt-1 text-2xl font-semibold">{t("48,600 of 45,000 MAD")}</p>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
          <motion.div
            className="h-full rounded-full bg-red-400"
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ duration: 1, delay: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
          />
        </div>
        <p className="tabular mt-2 text-xs font-medium text-red-300">{t("Over budget by 3,600.00 MAD")}</p>
        <div className="mt-5 grid gap-2">
          <PreviewRow tone="late" title={t("Book internet installation")} meta={t("6 days overdue")} />
          <PreviewRow tone="trip" title={t("Furniture pickup, Tangier")} meta={t("Leaves in 6 days")} />
        </div>
      </div>
      <motion.div
        initial={{ opacity: 0, x: rtl ? -12 : 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 1.1 }}
        className="absolute -bottom-6 -end-6 w-56 rounded-xl border border-white/10 bg-zinc-800/90 p-3 text-xs shadow-xl backdrop-blur"
      >
        <p className="text-zinc-400">{t("Estimated fuel cost")}</p>
        <p className="tabular mt-0.5 text-base font-semibold">{t("734 MAD")}</p>
        <div className="mt-2 h-1.5 rounded-full bg-gradient-to-r from-emerald-400 via-amber-300 to-red-400 rtl:bg-gradient-to-l" />
      </motion.div>
    </motion.div>
  );
}

function PreviewRow({ title, meta, tone }: { title: string; meta: string; tone: "late" | "trip" }) {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-white/[0.04] px-3 py-2">
      <span
        className={cn(
          "flex size-7 items-center justify-center rounded-md",
          tone === "late" ? "bg-red-500/15 text-red-300" : "bg-indigo-500/15 text-indigo-300",
        )}
      >
        {tone === "late" ? <TriangleAlert className="size-3.5" /> : <Plane className="size-3.5" />}
      </span>
      <span className="grid min-w-0">
        <span className="truncate text-sm">{title}</span>
        <span className={cn("text-xs", tone === "late" ? "text-red-300" : "text-zinc-400")}>{meta}</span>
      </span>
    </div>
  );
}

/** Password input with a show/hide eye; `aside` puts a link (e.g. "Forgot your password?") next to the label. */
export function PasswordField({
  id,
  label,
  error,
  hint,
  aside,
  ...props
}: { id: string; label: string; error?: string; hint?: ReactNode; aside?: ReactNode } & Omit<ComponentProps<typeof Input>, "type">) {
  const [shown, setShown] = useState(false);
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {aside}
      </div>
      <div className="relative">
        <Input
          id={id}
          name={id}
          type={shown ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="pe-10"
          {...props}
        />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          aria-pressed={shown}
          aria-label={shown ? t("Hide password") : t("Show password")}
          className="absolute inset-y-0 end-0 flex w-10 items-center justify-center rounded-e-md text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : (
        hint && (
          <div id={`${id}-hint`} className="text-xs text-muted-foreground">
            {hint}
          </div>
        )
      )}
    </div>
  );
}

/** Live check for the password rule, shown under the field while typing. */
export function PasswordRule({ value, min }: { value: string; min: number }) {
  const ok = value.length >= min;
  return (
    <span className={cn("inline-flex items-center gap-1.5 transition-colors", ok && "text-emerald-600 dark:text-emerald-400")}>
      <span
        className={cn(
          "flex size-4 items-center justify-center rounded-full border transition-colors",
          ok ? "border-transparent bg-emerald-500 text-white" : "border-muted-foreground/40",
        )}
      >
        {ok && <Check className="size-2.5" strokeWidth={3} />}
      </span>
      {t("At least {count} characters.", { count: min })}
    </span>
  );
}

/** Full-width submit button with a spinner while the request runs. */
export function SubmitButton({ busy, children, busyLabel }: { busy: boolean; children: ReactNode; busyLabel: string }) {
  return (
    <Button type="submit" disabled={busy} className="h-10 w-full">
      {busy && <Loader2 className="size-4 animate-spin" />}
      {busy ? busyLabel : children}
    </Button>
  );
}

/** Informational banner (not an error), e.g. "Your session expired". */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="flex items-start gap-2 rounded-lg border bg-muted/50 px-3 py-2.5 text-sm">
      <Info className="mt-0.5 size-4 shrink-0 text-primary" />
      <span>{children}</span>
    </div>
  );
}

/** "New here? Create an account" line under a form. */
export function AuthSwitch({ children }: { children: ReactNode }) {
  return <p className="text-center text-sm text-muted-foreground [&_a]:font-medium [&_a]:text-foreground [&_a]:underline-offset-4 hover:[&_a]:underline">{children}</p>;
}
