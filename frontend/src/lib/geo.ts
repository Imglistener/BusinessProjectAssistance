/**
 * Free OpenStreetMap services used by the trip map:
 * - Nominatim (place search), https://operations.osmfoundation.org/policies/nominatim/ : at most 1 request
 *   per second, no autocomplete; we only search when the user presses Enter.
 * - OSRM demo server (road distance), https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server : fair use,
 *   no guarantees. For production traffic, self-host OSRM or use a paid routing provider (see docs/deployment.md).
 */

export interface GeoPlace {
  name: string;
  lat: number;
  lng: number;
}

const NOMINATIM = "https://nominatim.openstreetmap.org";
const OSRM = "https://router.project-osrm.org";

let lastSearch = 0;

export async function searchPlaces(query: string): Promise<GeoPlace[]> {
  const wait = 1100 - (Date.now() - lastSearch);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastSearch = Date.now();
  const url = `${NOMINATIM}/search?format=jsonv2&limit=5&accept-language=fr,en&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error("Place search is unavailable right now.");
  const rows: { display_name: string; lat: string; lon: string }[] = await res.json();
  return rows.map((r) => ({ name: r.display_name, lat: Number(r.lat), lng: Number(r.lon) }));
}

export async function placeName(lat: number, lng: number): Promise<string | null> {
  const wait = 1100 - (Date.now() - lastSearch);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastSearch = Date.now();
  const res = await fetch(`${NOMINATIM}/reverse?format=jsonv2&zoom=14&accept-language=fr,en&lat=${lat}&lon=${lng}`);
  if (!res.ok) return null;
  const row: { display_name?: string } = await res.json();
  return row.display_name ?? null;
}

export interface Route {
  km: number;
  /** [lat, lng] points for drawing */
  path: [number, number][];
}

export async function drivingRoute(from: GeoPlace, to: GeoPlace): Promise<Route | null> {
  const coords = `${from.lng},${from.lat};${to.lng},${to.lat}`;
  const res = await fetch(`${OSRM}/route/v1/driving/${coords}?overview=simplified&geometries=geojson`);
  if (!res.ok) return null;
  const data = await res.json();
  const route = data?.routes?.[0];
  if (data?.code !== "Ok" || !route) return null;
  return {
    km: route.distance / 1000,
    path: (route.geometry.coordinates as [number, number][]).map(([lng, lat]) => [lat, lng]),
  };
}
