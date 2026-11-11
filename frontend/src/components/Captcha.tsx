import type {} from "altcha/types/react";
import { useEffect, useImperativeHandle, useRef, useState, type CSSProperties, type Ref } from "react";
import { API_BASE } from "../api/client";
import { getLang } from "../i18n";

/** What the form needs: the solution to send, or null while the box isn't ticked. */
export interface CaptchaHandle {
  /** After a failed submit: the solution was used, so the visitor ticks the box again. */
  reset(): void;
}

type Status = "loading" | "on" | "off";

// The app's colours, so the widget follows light and dark mode.
const STYLE = {
  "--altcha-color-base": "var(--card)",
  "--altcha-color-base-content": "var(--card-foreground)",
  "--altcha-color-primary": "var(--primary)",
  "--altcha-color-primary-content": "var(--primary-foreground)",
  "--altcha-color-error": "var(--destructive)",
  "--altcha-color-success": "oklch(0.596 0.145 163.225)", // emerald-600, as elsewhere in the app
  "--altcha-color-success-content": "#fff",
  "--altcha-border-color": "var(--border)",
  "--altcha-checkbox-border-color": "var(--input)",
  "--altcha-border-radius": "calc(var(--radius) - 2px)",
  "--altcha-max-width": "100%",
} as CSSProperties;

// Widget translations for the app's languages (English is built in).
const LANGUAGE_FILES: Record<string, () => Promise<unknown>> = {
  fr: () => import("altcha/i18n/fr-fr"),
  ar: () => import("altcha/i18n/ar"),
};
const WIDGET_LANGUAGE: Record<string, string> = { en: "en", fr: "fr-fr", ar: "ar" };

/**
 * "I'm not a robot" box for login and signup (ALTCHA proof of work, solved in the browser; no third party).
 * Calls onChange with the solution once ticked, and with null when it expires or is reset. When the server has
 * the captcha turned off, it renders nothing and reports "" (nothing to send).
 */
export function Captcha({ onChange, ref }: { onChange(payload: string | null): void; ref?: Ref<CaptchaHandle> }) {
  const [status, setStatus] = useState<Status>("loading");
  const widget = useRef<HTMLElement & { reset?: () => void }>(null);
  const changed = useRef(onChange);
  changed.current = onChange;

  useImperativeHandle(ref, () => ({
    reset() {
      widget.current?.reset?.();
      changed.current(status === "off" ? "" : null);
    },
  }));

  useEffect(() => {
    let live = true;
    (async () => {
      let on = true;
      try {
        const r = await fetch(`${API_BASE}/auth/captcha`);
        on = !(r.ok && (await r.json()).enabled === false);
      } catch {
        // Server unreachable: show the box anyway; the form will report the connection problem.
      }
      if (on) {
        await import("altcha");
        await LANGUAGE_FILES[getLang()]?.();
      }
      if (!live) return;
      setStatus(on ? "on" : "off");
      if (!on) changed.current("");
    })();
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const el = widget.current;
    if (status !== "on" || !el) return;
    const onState = (e: Event) => {
      const { state, payload } = (e as CustomEvent<{ state: string; payload?: string }>).detail;
      changed.current(state === "verified" && payload ? payload : null);
    };
    el.addEventListener("statechange", onState);
    return () => el.removeEventListener("statechange", onState);
  }, [status]);

  if (status === "off") return null;
  if (status === "loading") return <div className="h-[66px] rounded-md border border-dashed" aria-hidden="true" />;
  return (
    <altcha-widget
      ref={widget}
      challenge={`${API_BASE}/auth/captcha`}
      language={WIDGET_LANGUAGE[getLang()] ?? "en"}
      type="checkbox"
      style={STYLE}
      data-testid="captcha"
    />
  );
}
