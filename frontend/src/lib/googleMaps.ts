/**
 * Loads the Google Maps JavaScript API (with Places) once, when VITE_GOOGLE_MAPS_API_KEY is set.
 * Without a key the app uses its built-in city list instead, so nothing here runs.
 */

// The Maps API has no bundled types here; keep its surface typed loosely and in one place.
export type Google = any;

declare global {
  interface Window {
    google?: Google;
    __bpaMapsReady?: () => void;
  }
}

export const MAPS_KEY: string | undefined = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || undefined;

let loading: Promise<Google> | null = null;

export function loadGoogleMaps(): Promise<Google> {
  if (!MAPS_KEY) return Promise.reject(new Error("No Google Maps key"));
  if (window.google?.maps?.places) return Promise.resolve(window.google);
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    window.__bpaMapsReady = () => resolve(window.google);
    const script = document.createElement("script");
    script.src =
      "https://maps.googleapis.com/maps/api/js" +
      `?key=${encodeURIComponent(MAPS_KEY)}&libraries=places&v=weekly&callback=__bpaMapsReady`;
    script.async = true;
    script.onerror = () => {
      loading = null;
      reject(new Error("Google Maps failed to load"));
    };
    document.head.appendChild(script);
  });
  return loading;
}
