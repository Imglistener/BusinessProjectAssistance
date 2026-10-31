import { Check, Languages } from "lucide-react";
import { api, tokenStore } from "../api/client";
import { LANGUAGES, applyLanguage, getLang, isRtl, t, type Lang } from "../i18n";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/** Saves the choice on the account (for emails and notifications), then reloads the app in the new language. */
export async function switchLanguage(lang: Lang): Promise<void> {
  applyLanguage(lang);
  if (tokenStore.get()) await api("/auth/me", { method: "PATCH", body: { locale: lang } }).catch(() => undefined);
  window.location.reload();
}

/** Globe button with the language name; `iconOnly` for tight spaces (collapsed sidebar). */
export function LanguagePicker({ className, iconOnly = false }: { className?: string; iconOnly?: boolean }) {
  const current = LANGUAGES.find((l) => l.code === getLang()) ?? LANGUAGES[0];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size={iconOnly ? "icon" : "sm"}
          className={cn("gap-2", className)}
          aria-label={t("Language")}
        >
          <Languages className="size-4" />
          {!iconOnly && <span lang={current.code}>{current.label}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={isRtl() ? "start" : "end"} className="min-w-36">
        {LANGUAGES.map((l) => (
          <DropdownMenuItem key={l.code} lang={l.code} onSelect={() => l.code !== current.code && switchLanguage(l.code)}>
            <span className="flex-1">{l.label}</span>
            {l.code === current.code && <Check className="size-4 text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
