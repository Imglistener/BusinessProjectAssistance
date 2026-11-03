/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

// The captcha widget's French translation ships without a declaration file.
declare module "altcha/i18n/fr-fr";
