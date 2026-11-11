import "@fontsource-variable/geist";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/instrument-sans";
// Arabic script only (unicode-range), so Latin pages don't download it.
import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { OrgProvider } from "./auth/OrgContext";
import { MotionConfig } from "motion/react";
import { Direction } from "radix-ui";
import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useReduceMotion } from "./hooks/use-reduce-motion";
import { isRtl } from "./i18n";
// globals.css declares the cascade layers, so it must come before the older index.css.
import "./styles/globals.css";
import "./index.css";

/** Motion's animations follow the app's "Reduce motion" setting, like the CSS ones. */
function MotionRoot({ children }: { children: ReactNode }) {
  const reduce = useReduceMotion();
  return <MotionConfig reducedMotion={reduce ? "always" : "never"}>{children}</MotionConfig>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <OrgProvider>
          {/* Radix components (tabs, menus, selects) lay out right to left in Arabic; switching language reloads. */}
          <Direction.Provider dir={isRtl() ? "rtl" : "ltr"}>
            <TooltipProvider delayDuration={300}>
              <MotionRoot>
                <App />
              </MotionRoot>
            </TooltipProvider>
          </Direction.Provider>
        </OrgProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
