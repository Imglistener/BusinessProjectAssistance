import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Loader2, MapPin, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { placeName, searchPlaces, type GeoPlace } from "../../lib/geo";
import { t } from "../../i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface Location {
  address: string;
  lat: number | null;
  lng: number | null;
}

/**
 * Find a warehouse's address and pin it: search (press Enter) or click the map. Uses the same free
 * OpenStreetMap services as trip routes; the address stays editable as plain text.
 */
export function LocationPicker({ value, onChange }: { value: Location; onChange(next: Location): void }) {
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const valueRef = useRef(value);
  valueRef.current = value;
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeoPlace[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!mapEl.current || map.current) return;
    const start: L.LatLngExpression = value.lat !== null && value.lng !== null ? [value.lat, value.lng] : [31.8, -7.1];
    const m = L.map(mapEl.current, { scrollWheelZoom: false }).setView(start, value.lat !== null ? 13 : 5);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    m.on("click", (ev: L.LeafletMouseEvent) => {
      const { lat, lng } = ev.latlng;
      onChangeRef.current({ ...valueRef.current, lat, lng });
      placeName(lat, lng)
        .then((name) => name && onChangeRef.current({ address: name, lat, lng }))
        .catch(() => undefined);
    });
    map.current = m;
    // The dialog animates open; let Leaflet measure the final size.
    const timer = window.setTimeout(() => m.invalidateSize(), 250);
    return () => {
      window.clearTimeout(timer);
      m.remove();
      map.current = null;
      marker.current = null;
    };
    // The map is created once; later position changes are handled below.
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (value.lat === null || value.lng === null) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const at: L.LatLngExpression = [value.lat, value.lng];
    if (!marker.current) {
      marker.current = L.circleMarker(at, { radius: 9, color: "#fff", weight: 3, fillColor: "#4b4fe0", fillOpacity: 1 }).addTo(m);
    } else {
      marker.current.setLatLng(at);
    }
    m.setView(at, Math.max(m.getZoom(), 13));
  }, [value.lat, value.lng]);

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setMessage(null);
    try {
      const found = await searchPlaces(query.trim());
      setResults(found);
      if (!found.length) setMessage(t("No place found. Try another spelling, or click the map."));
    } catch {
      setMessage(t("Search failed."));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="grid gap-3">
      <div className="relative">
        <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
          placeholder={t("City or address, then Enter")}
          aria-label={t("Search for the address")}
          className="ps-9"
        />
        {searching && <Loader2 className="absolute end-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />}
      </div>
      {results && results.length > 0 && (
        <ul className="grid max-h-40 gap-1 overflow-auto rounded-lg border p-1 text-sm">
          {results.map((r) => (
            <li key={`${r.lat},${r.lng}`}>
              <Button
                type="button"
                variant="ghost"
                className="h-auto w-full justify-start whitespace-normal py-1.5 text-start font-normal"
                onClick={() => {
                  onChange({ address: r.name, lat: r.lat, lng: r.lng });
                  setResults(null);
                }}
              >
                <MapPin className="size-4 shrink-0 text-primary" />
                {r.name}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {message && <p className="text-xs text-muted-foreground">{message}</p>}
      <div ref={mapEl} className="h-56 overflow-hidden rounded-lg border" dir="ltr" aria-label={t("Map: click to place the warehouse")} />
      <p className="text-xs text-muted-foreground">
        {t("Map, search and routing by OpenStreetMap services; the places you look up are sent to them.")}
      </p>
    </div>
  );
}
