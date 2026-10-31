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
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { OrgProvider } from "./auth/OrgContext";
import { TooltipProvider } from "@/components/ui/tooltip";
// globals.css declares the cascade layers, so it must come before the older index.css.
import "./styles/globals.css";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <OrgProvider>
          <TooltipProvider delayDuration={300}>
            <App />
          </TooltipProvider>
        </OrgProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
