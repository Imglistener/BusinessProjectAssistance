import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/instrument-sans";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { OrgProvider } from "./auth/OrgContext";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
