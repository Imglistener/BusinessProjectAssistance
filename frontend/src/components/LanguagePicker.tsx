import { api, tokenStore } from "../api/client";
import { LANGUAGES, applyLanguage, getLang, t, type Lang } from "../i18n";

/** Saves the choice on the account (for emails and notifications), then reloads the app in the new language. */
export async function switchLanguage(lang: Lang): Promise<void> {
  applyLanguage(lang);
  if (tokenStore.get()) await api("/auth/me", { method: "PATCH", body: { locale: lang } }).catch(() => undefined);
  window.location.reload();
}

export function LanguagePicker({ className = "" }: { className?: string }) {
  return (
    <label className={`lang-picker ${className}`.trim()}>
      <span className="visually-hidden">{t("Language")}</span>
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" className="lang-picker__icon">
        <path
          d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3.5 9h17M3.5 15h17M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
        />
      </svg>
      <select value={getLang()} onChange={(e) => switchLanguage(e.target.value as Lang)}>
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code} lang={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
