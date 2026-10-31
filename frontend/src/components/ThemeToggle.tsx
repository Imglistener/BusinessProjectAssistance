import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";

const KEY = "bpa.theme";

function isDark() {
  return document.documentElement.classList.contains("dark");
}

/** Light/dark switch. The choice is remembered; without one, the system setting is used (see index.html). */
export function ThemeToggle({ className }: { className?: string }) {
  const [dark, setDark] = useState(isDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const label = dark ? t("Switch to light mode") : t("Switch to dark mode");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={label}
          className={cn("relative", className)}
          onClick={() => {
            const next = !dark;
            setDark(next);
            try {
              localStorage.setItem(KEY, next ? "dark" : "light");
            } catch {
              /* storage unavailable: lasts until reload */
            }
          }}
        >
          <Sun className="size-4 scale-100 rotate-0 transition-transform duration-300 dark:scale-0 dark:-rotate-90" />
          <Moon className="absolute size-4 scale-0 rotate-90 transition-transform duration-300 dark:scale-100 dark:rotate-0" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
