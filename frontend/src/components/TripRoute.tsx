import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { FuelEstimate, TravelReference, Trip } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatMoney, formatNumber } from "../lib/format";
import { drivingRoute, placeName, searchPlaces, type GeoPlace } from "../lib/geo";
import { FormError } from "./AuthLayout";
import { t } from "../i18n";
import { tx } from "../i18n/rich";

interface Place {
  name: string;
  lat: number | null;
  lng: number | null;
}

const SOURCE_LABEL: Record<string, string> = {
  route: t("road route (OpenStreetMap)"),
  straight_line: t("straight-line estimate"),
  manual: t("entered by hand"),
};

let referenceCache: Promise<TravelReference> | null = null;
const loadReference = () => (referenceCache ??= api<TravelReference>("/travel/reference"));

/** Route, vehicle and fuel estimate for one trip. */
export function TripRoute({ trip, onSaved }: { trip: Trip; onSaved(trip: Trip): void }) {
  const [ref, setRef] = useState<TravelReference | null>(null);
  const [editing, setEditing] = useState(false);
  const r = trip.route;
  const hasRoute = r.distance_km !== null;

  useEffect(() => {
    loadReference()
      .then(setRef)
      .catch(() => setRef(null));
  }, []);

  const vehicle = ref?.vehicles.find((v) => v.type === (r.vehicle_type ?? ref.default_vehicle));

  return (
    <section className="card" aria-labelledby="route-heading">
      <div className="section-head">
        <h2 id="route-heading">{t("Route & fuel")}</h2>
        {trip.can_edit && !editing && (
          <button type="button" className="btn btn--secondary no-print" onClick={() => setEditing(true)}>
            {hasRoute ? t("Change route") : t("Set route")}
          </button>
        )}
      </div>

      {editing && ref && (
        <RouteEditor
          trip={trip}
          reference={ref}
          onCancel={() => setEditing(false)}
          onSaved={(x) => {
            setEditing(false);
            onSaved(x);
          }}
        />
      )}

      {!editing && (
        <>
          {hasRoute ? (
            <dl className="route-facts">
              <div>
                <dt>{t("From")}</dt>
                <dd>{r.origin ?? "—"}</dd>
              </div>
              <div>
                <dt>{t("To")}</dt>
                <dd>{trip.destination}</dd>
              </div>
              <div>
                <dt>{t("Distance")}</dt>
                <dd>
                  {t("{km} km one way", { km: formatNumber(r.distance_km ?? 0) })}
                  <small>{SOURCE_LABEL[r.distance_source ?? "manual"]}</small>
                </dd>
              </div>
              <div>
                <dt>{t("Vehicle")}</dt>
                <dd>
                  {r.vehicle_count > 1 ? `${r.vehicle_count} × ` : ""}
                  {vehicle ? t(vehicle.label) : "—"}
                  <small>{r.round_trip ? t("Round trip") : t("One way")}</small>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">
              {t("Set where the trip starts and ends to estimate the fuel cost.")}
              {!trip.can_edit && ` ${t("Ask the trip's organizer to add it.")}`}
            </p>
          )}
          {hasRoute && <FuelEstimateCard trip={trip} />}
        </>
      )}
    </section>
  );
}

function RouteEditor({
  trip,
  reference,
  onSaved,
  onCancel,
}: {
  trip: Trip;
  reference: TravelReference;
  onSaved(trip: Trip): void;
  onCancel(): void;
}) {
  const r = trip.route;
  const [from, setFrom] = useState<Place>({ name: r.origin ?? "", lat: r.origin_lat, lng: r.origin_lng });
  const [to, setTo] = useState<Place>({ name: trip.destination, lat: r.destination_lat, lng: r.destination_lng });
  const [routeKm, setRouteKm] = useState<string | null>(r.distance_source === "route" ? r.distance_km : null);
  const [manualKm, setManualKm] = useState(r.distance_source === "manual" ? (r.distance_km ?? "") : "");
  const [vehicleType, setVehicleType] = useState(r.vehicle_type ?? reference.default_vehicle);
  const [count, setCount] = useState(String(r.vehicle_count || 1));
  const [roundTrip, setRoundTrip] = useState(r.round_trip);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Stable, so the map doesn't re-request directions on every render.
  const handleRoute = useCallback((km: string | null) => {
    setRouteKm(km);
    if (km) setManualKm("");
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      origin: from.name.trim() || null,
      origin_lat: from.lat,
      origin_lng: from.lng,
      destination_lat: to.lat,
      destination_lng: to.lng,
      vehicle_type: vehicleType,
      vehicle_count: Math.max(1, Math.min(50, Number(count) || 1)),
      round_trip: roundTrip,
    };
    if (to.name.trim() && to.name.trim() !== trip.destination) body.destination = to.name.trim();
    if (manualKm.trim()) {
      body.distance_km = manualKm.trim().replace(",", ".");
      body.distance_source = "manual";
    } else if (routeKm) {
      body.distance_km = routeKm;
      body.distance_source = "route";
    } else {
      // The server works out a straight-line estimate from the coordinates (or clears the distance).
      body.distance_km = null;
    }
    try {
      const res = await api<{ trip: Trip }>(`/trips/${trip.id}`, { method: "PATCH", body });
      onSaved(res.trip);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="route-editor">
      <FormError message={error} />
      <MapPicker reference={reference} from={from} to={to} onFrom={setFrom} onTo={setTo} onRoute={handleRoute} />

      <div className="route-editor__grid">
        <label className="filter">
          <span className="filter__label">{t("Distance one way (km)")}</span>
          <input
            inputMode="decimal"
            placeholder={routeKm ? t("{routeKm} from the map", { routeKm: routeKm }) : t("Optional: overrides the estimate")}
            value={manualKm}
            onChange={(e) => setManualKm(e.target.value)}
          />
        </label>
        <label className="filter">
          <span className="filter__label">{t("Vehicle")}</span>
          <select value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}>
            {reference.vehicles.map((v) => (
              <option key={v.type} value={v.type}>
                {t(v.label)} — {v.l_per_100km_low}–{v.l_per_100km_high} L/100 km</option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span className="filter__label">{t("Vehicles")}</span>
          <input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className="check filter__check">
          <input type="checkbox" checked={roundTrip} onChange={(e) => setRoundTrip(e.target.checked)} />
          {t("Round trip")}
        </label>
      </div>
      <div className="form__actions">
        <button type="button" className="btn btn--primary" onClick={save} disabled={busy}>
          {busy ? t("Saving…") : t("Save route")}
        </button>
        <button type="button" className="btn btn--quiet" onClick={onCancel}>
          {t("Cancel")}
        </button>
      </div>
    </div>
  );
}

/**
 * Leaflet + OpenStreetMap. Search (built-in cities first, then OpenStreetMap search on Enter) or click the map to
 * set the start, then the finish. The road distance comes from OSRM; without a route, the server falls back to a
 * straight-line estimate.
 */
function MapPicker({
  reference,
  from,
  to,
  onFrom,
  onTo,
  onRoute,
}: {
  reference: TravelReference;
  from: Place;
  to: Place;
  onFrom(p: Place): void;
  onTo(p: Place): void;
  onRoute(km: string | null): void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.LayerGroup | null>(null);
  const [active, setActive] = useState<"from" | "to">(from.lat === null ? "from" : "to");
  const activeRef = useRef(active);
  activeRef.current = active;
  const setters = useRef({ onFrom, onTo });
  setters.current = { onFrom, onTo };
  const [status, setStatus] = useState("");

  const setPoint = useCallback((which: "from" | "to", p: Place) => {
    (which === "from" ? setters.current.onFrom : setters.current.onTo)(p);
  }, []);

  // Create the map once.
  useEffect(() => {
    if (!mapEl.current || map.current) return;
    const m = L.map(mapEl.current, { scrollWheelZoom: false }).setView([31.8, -7.1], 5);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    layers.current = L.layerGroup().addTo(m);
    m.on("click", (ev: L.LeafletMouseEvent) => {
      const which = activeRef.current;
      const { lat, lng } = ev.latlng;
      setPoint(which, { name: `${lat.toFixed(4)}, ${lng.toFixed(4)}`, lat, lng });
      setActive(which === "from" ? "to" : "from");
      placeName(lat, lng)
        .then((name) => name && setPoint(which, { name, lat, lng }))
        .catch(() => undefined);
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, [setPoint]);

  // Markers, route line and road distance whenever the ends change.
  useEffect(() => {
    const m = map.current;
    const group = layers.current;
    if (!m || !group) return;
    group.clearLayers();
    const points: L.LatLngExpression[] = [];
    for (const [p, colour, label] of [
      [from, "#2f9e6b", t("Start")],
      [to, "#d9534f", t("Finish")],
    ] as const) {
      if (p.lat === null || p.lng === null) continue;
      points.push([p.lat, p.lng]);
      L.circleMarker([p.lat, p.lng], { radius: 9, color: "#fff", weight: 3, fillColor: colour, fillOpacity: 1 })
        .bindTooltip(`${label}: ${p.name}`)
        .addTo(group);
    }
    if (points.length === 1) m.setView(points[0], 9);
    if (points.length < 2 || from.lat === null || from.lng === null || to.lat === null || to.lng === null) {
      onRoute(null);
      return;
    }
    m.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
    let cancelled = false;
    setStatus(t("Finding the road route…"));
    drivingRoute({ name: from.name, lat: from.lat, lng: from.lng }, { name: to.name, lat: to.lat, lng: to.lng })
      .then((route) => {
        if (cancelled) return;
        if (route) {
          L.polyline(route.path, { color: "#2b3ccf", weight: 5, opacity: 0.8 }).addTo(group);
          onRoute(route.km.toFixed(1));
          setStatus(t("Road route: {km} km one way.", { km: formatNumber(route.km.toFixed(1)) }));
        } else {
          onRoute(null);
          setStatus(t("No road route found; the distance will be a straight-line estimate."));
        }
      })
      .catch(() => {
        if (cancelled) return;
        onRoute(null);
        setStatus(t("The routing service didn't answer; the distance will be a straight-line estimate."));
      });
    return () => {
      cancelled = true;
    };
  }, [from.lat, from.lng, to.lat, to.lng, from.name, to.name, onRoute]);

  return (
    <div className="map-picker">
      <div className="route-editor__grid">
        <PlaceSearch
          label={t("From")}
          value={from}
          reference={reference}
          onFocus={() => setActive("from")}
          onPick={(p) => {
            setPoint("from", p);
            setActive("to");
          }}
        />
        <PlaceSearch
          label={t("To")}
          value={to}
          reference={reference}
          onFocus={() => setActive("to")}
          onPick={(p) => setPoint("to", p)}
        />
      </div>
      <p className="muted route-editor__hint">
        {active === "from"
          ? tx("Type a city or address and press Enter, or click the map to set the {point}.", {
              point: <strong>{t("start")}</strong>,
            })
          : tx("Type a city or address and press Enter, or click the map to set the {point}.", {
              point: <strong>{t("finish")}</strong>,
            })}
        {status ? ` ${status}` : ""}
      </p>
      <div ref={mapEl} className="map-picker__map" aria-label={t("Map: click to set the start or finish")} />
      <p className="muted map-picker__credit">
        {t("Map, search and routing by OpenStreetMap services; the places you look up are sent to them.")}
      </p>
    </div>
  );
}

function PlaceSearch({
  label,
  value,
  reference,
  onPick,
  onFocus,
}: {
  label: string;
  value: Place;
  reference: TravelReference;
  onPick(p: Place): void;
  onFocus(): void;
}) {
  const [text, setText] = useState(value.name);
  const [results, setResults] = useState<GeoPlace[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setText(value.name), [value.name]);

  const search = async () => {
    const q = text.trim();
    if (!q) return;
    const city = reference.cities.find((c) => c.name.toLowerCase() === q.toLowerCase());
    if (city) {
      onPick({ name: city.name, lat: city.lat, lng: city.lng });
      setResults(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const found = await searchPlaces(q);
      if (found.length === 1) {
        onPick(found[0]);
        setResults(null);
      } else {
        setResults(found);
        if (!found.length) setError(t("No place found. Try another spelling, or click the map."));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("Search failed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="filter place-search">
      <label className="filter__label" htmlFor={`place-${label}`}>
        {label}
      </label>
      <input
        id={`place-${label}`}
        list="bpa-cities"
        value={text}
        placeholder={t("City or address, then Enter")}
        onFocus={onFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            search();
          }
        }}
        onBlur={() => {
          const city = reference.cities.find((c) => c.name.toLowerCase() === text.trim().toLowerCase());
          if (city && city.name !== value.name) onPick({ name: city.name, lat: city.lat, lng: city.lng });
        }}
      />
      <datalist id="bpa-cities">
        {reference.cities.map((c) => (
          <option key={c.name} value={c.name} />
        ))}
      </datalist>
      {busy && <span className="muted">{t("Searching…")}</span>}
      {error && <span className="field__message field__message--error">{error}</span>}
      {results && results.length > 1 && (
        <ul className="place-search__results">
          {results.map((r) => (
            <li key={`${r.lat},${r.lng}`}>
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  onPick(r);
                  setResults(null);
                }}
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FuelEstimateCard({ trip }: { trip: Trip }) {
  const [estimate, setEstimate] = useState<FuelEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [variance, setVariance] = useState(10);

  useEffect(() => {
    setError(null);
    api<{ estimate: FuelEstimate }>(`/trips/${trip.id}/fuel-estimate?variance=${variance}`)
      .then((r) => setEstimate(r.estimate))
      .catch((e) => {
        setEstimate(null);
        setError(e instanceof ApiError && e.code === "estimate_unavailable" ? e.message : errorMessage(e));
      });
  }, [trip.id, trip.route, variance]);

  if (error) {
    return (
      <div className="fuel fuel--empty">
        <p>{error}</p>
        {error.includes(t("Fuel prices")) && (
          <Link to="/app/settings" className="no-print">
            {t("Set fuel prices")}
          </Link>
        )}
      </div>
    );
  }
  if (!estimate) return <p className="muted">{t("Estimating…")}</p>;

  const c = estimate.currency;
  const low = Number(estimate.cost.low);
  const high = Number(estimate.cost.high);
  const mid = Number(estimate.cost.expected);
  const pos = high > low ? ((mid - low) / (high - low)) * 100 : 50;
  const question = t("Explain the fuel cost estimate for the trip “{title}” and how we could reduce it.", { title: trip.title });

  return (
    <div className="fuel">
      <div className="fuel__head">
        <div>
          <span className="fuel__label">{t("Estimated fuel cost")}</span>
          <span className="fuel__value">{formatMoney(estimate.cost.expected, c)}</span>
          <span className="muted">
            {t("likely between {low} and {high}", {
              low: formatMoney(estimate.cost.low, c),
              high: formatMoney(estimate.cost.high, c),
            })}
          </span>
        </div>
        <div className="fuel__side">
          <span className="fuel__label">{t("Fuel")}</span>
          <span>
            {t("{litres} L {fuel}", { litres: formatNumber(estimate.litres.expected), fuel: t(estimate.vehicle.fuel) })}
          </span>
          <span className="muted">
            {t("{km} km at {price} {currency}/L", {
              km: formatNumber(estimate.total_km),
              price: formatNumber(estimate.fuel_price.price_per_litre),
              currency: c,
            })}
          </span>
        </div>
      </div>
      <div
        className="fuel__range"
        role="img"
        aria-label={t("Range from {low} to {high}", { low: formatMoney(estimate.cost.low, c), high: formatMoney(estimate.cost.high, c) })}
      >
        <span className="fuel__marker" style={{ left: `${pos}%` }} />
      </div>
      <div className="fuel__range-labels">
        <span>{formatMoney(estimate.cost.low, c)}</span>
        <span>{formatMoney(estimate.cost.high, c)}</span>
      </div>

      <label className="fuel__variance no-print">
        <span className="filter__label">{t("Allow for detours and traffic: {pct}%", { pct: variance })}</span>
        <input
          type="range"
          min={0}
          max={30}
          step={5}
          value={variance}
          onChange={(e) => setVariance(Number(e.target.value))}
        />
      </label>

      {estimate.warnings.length > 0 && (
        <ul className="fuel__warnings">
          {estimate.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <details className="fuel__assumptions">
        <summary>{t("How this is calculated")}</summary>
        <ul>
          {estimate.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </details>
      <Link
        className="btn btn--secondary btn--link no-print fuel__ask"
        to={`/app/assistant?project=${trip.project_id}&q=${encodeURIComponent(question)}`}
      >
        {t("Ask the assistant about this")}
      </Link>
    </div>
  );
}
