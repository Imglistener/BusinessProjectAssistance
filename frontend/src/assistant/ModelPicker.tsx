import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { AIProviderInfo } from "../api/models";
import { getLocale, t } from "../i18n";
import { useAssistant } from "./AssistantContext";

const timeFmt = new Intl.DateTimeFormat(getLocale(), { hour: "2-digit", minute: "2-digit" });
const dayTimeFmt = new Intl.DateTimeFormat(getLocale(), { weekday: "short", hour: "2-digit", minute: "2-digit" });

function resetTime(iso: string): string {
  const d = new Date(iso);
  return (d.toDateString() === new Date().toDateString() ? timeFmt : dayTimeFmt).format(d);
}

function note(p: AIProviderInfo): string {
  if (p.available) return p.model.split("/").pop() ?? p.model;
  // Short limits reset within a minute or so; a clock time would look like an error.
  if (p.available_at && (p.daily || Date.parse(p.available_at) - Date.now() > 90_000))
    return t(p.daily ? "Daily limit reached. Back at {time}" : "Limit reached. Back at {time}", { time: resetTime(p.available_at) });
  return t("Limit reached. Back in a moment");
}

/** Which AI answers, in the corner of the composer. One whose limit is reached is greyed out until it resets. */
export function ModelPicker() {
  const { providers, provider, setProvider, busy } = useAssistant();
  if (!provider) return null;
  if (providers.length === 1) return <span className="model-picker model-picker--only">{provider.label}</span>;
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild disabled={busy}>
        <button type="button" className="model-picker" aria-label={t("AI model: {name}", { name: provider.label })}>
          {provider.label}
          <ChevronDown aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="end" className="w-64">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{t("Answer with")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={provider.id} onValueChange={setProvider}>
          {providers.map((p) => (
            <DropdownMenuRadioItem key={p.id} value={p.id} disabled={!p.available} className="py-2">
              <span className="grid gap-0.5">
                <span className="font-medium">{p.label}</span>
                <span className="text-xs text-muted-foreground">{note(p)}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
