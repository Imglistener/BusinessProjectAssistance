/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Optional: enables the map picker on trips. */
  readonly VITE_GOOGLE_MAPS_API_KEY?: string;
}
