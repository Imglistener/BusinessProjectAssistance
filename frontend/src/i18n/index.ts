/**
 * Translations. The English text is the key, so anything without a translation shows in English.
 *
 *   t("Add expense")                          -> "Ajouter une dépense"
 *   t("Due in {days} days", { days: 3 })      -> placeholders in {braces}
 *   t("{count} overdue tasks", { count: n })  -> plural forms when the entry is an object
 *
 * The language lives here (not in React state) so `t` works in any module. Changing it reloads the
 * app tree (see LanguageProvider), which is simpler than threading a hook through every component.
 */
import ar from "./ar";
import en from "./en";
import fr from "./fr";

export type Lang = "en" | "fr" | "ar";
export type Entry = string | Partial<Record<Intl.LDMLPluralRule, string>>;
export type Dictionary = Record<string, Entry>;

export const LANGUAGES: { code: Lang; label: string; dir: "ltr" | "rtl" }[] = [
  { code: "en", label: "English", dir: "ltr" },
  { code: "fr", label: "Français", dir: "ltr" },
  { code: "ar", label: "العربية", dir: "rtl" },
];

const DICTS: Record<Lang, Dictionary> = { en, fr, ar };
/** Intl locale per language. fr-FR rather than fr-MA: spaces between thousands (1 850,50), as Moroccan businesses write them. */
export const LOCALES: Record<Lang, string> = { en: "en-GB", fr: "fr-FR", ar: "ar-MA" };
const STORAGE_KEY = "bpa.lang";

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "fr" || saved === "ar") return saved;
  } catch {
    /* storage unavailable */
  }
  const nav = (navigator.language || "en").slice(0, 2);
  return nav === "fr" || nav === "ar" ? nav : "en";
}

let current: Lang = detect();

export const getLang = (): Lang => current;
export const getLocale = (): string => LOCALES[current];
export const isRtl = (): boolean => LANGUAGES.find((l) => l.code === current)?.dir === "rtl";

/** Apply the language to the document (lang, dir) and remember it. Callers re-render the app. */
export function applyLanguage(lang: Lang): void {
  current = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* storage unavailable */
  }
  document.documentElement.lang = lang;
  document.documentElement.dir = isRtl() ? "rtl" : "ltr";
}

applyLanguage(current);

function fill(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

function pick(entry: Entry, count: number | undefined): string | undefined {
  if (typeof entry === "string") return entry;
  const rule = new Intl.PluralRules(LOCALES[current]).select(count ?? 0);
  return entry[rule] ?? entry.other;
}

export function t(key: string, vars?: Record<string, string | number>): string {
  const count = typeof vars?.count === "number" ? vars.count : undefined;
  const entry = DICTS[current][key] ?? DICTS.en[key];
  const text = entry === undefined ? key : (pick(entry, count) ?? key);
  return fill(text, vars);
}
