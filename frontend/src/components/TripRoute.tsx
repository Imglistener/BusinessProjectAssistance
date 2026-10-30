import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { FuelEstimate, TravelReference, Trip } from "../api/models";
import { errorMessage } from "../lib/errors";
import { formatMoney } from "../lib/format";
import { MAPS_KEY, loadGoogleMaps, type Google } from "../lib/googleMaps";
import { FormError } from "./AuthLayout";

interface Place {
  name: string;
  lat: number | null;
  lng: number | null;
}

const SOURCE_LABEL: Record<string, string> = {
  route: "road route from the map",
  straight_line: "straight-line estimate",
  manual: "entered by hand",
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
        <h2 id="route-heading">Route &amp; fuel</h2>
        {trip.can_edit && !editing && (
          <button type="button" className="btn btn--secondary no-print" onClick={() => setEditing(true)}>
            {hasRoute ? "Change route" : "Set route"}
          </button>
        )}
      </div>

      {editing && ref && (
        <RouteEditor
          trip={trip}
          reference={ref}
          onCancel={() => setEditing(false)}
          onSaved={(t) => {
            setEditing(false);
            onSaved(t);
          }}
        />
      )}

      {!editing && (
        <>
          {hasRoute ? (
            <dl className="route-facts">
              <div>
                <dt>From</dt>
                <dd>{r.origin ?? "—"}</dd>
              </div>
              <div>
                <dt>To</dt>
                <dd>{trip.destination}</dd>
              </div>
              <div>
                <dt>Distance</dt>
                <dd>
                  {Number(r.distance_km).toLocaleString("en-US")} km one way
                  <small>{SOURCE_LABEL[r.distance_source ?? "manual"]}</small>
                </dd>
              </div>
              <div>
                <dt>Vehicle</dt>
                <dd>
                  {r.vehicle_count > 1 ? `${r.vehicle_count} × ` : ""}
                  {vehicle?.label ?? "—"}
                  <small>{r.round_trip ? "Round trip" : "One way"}</small>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">
              Set where the trip starts and ends to estimate the fuel cost.
              {!trip.can_edit && " Ask the trip's organizer to add it."}
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
      {MAPS_KEY ? (
        <MapPicker from={from} to={to} onFrom={setFrom} onTo={setTo} onRoute={handleRoute} />
      ) : (
        <CityPicker reference={reference} from={from} to={to} onFrom={setFrom} onTo={setTo} />
      )}

      <div className="route-editor__grid">
        <label className="filter">
          <span className="filter__label">Distance one way (km)</span>
          <input
            inputMode="decimal"
            placeholder={routeKm ? `${routeKm} from the map` : "Optional: overrides the estimate"}
            value={manualKm}
            onChange={(e) => setManualKm(e.target.value)}
          />
        </label>
        <label className="filter">
          <span className="filter__label">Vehicle</span>
          <select value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}>
            {reference.vehicles.map((v) => (
              <option key={v.type} value={v.type}>
                {v.label} — {v.l_per_100km_low}–{v.l_per_100km_high} L/100 km
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span className="filter__label">Vehicles</span>
          <input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className="check filter__check">
          <input type="checkbox" checked={roundTrip} onChange={(e) => setRoundTrip(e.target.checked)} />
          Round trip
        </label>
      </div>
      {!MAPS_KEY && (
        <p className="muted route-editor__hint">
          Without a map, the distance is the straight line between the two cities × {reference.road_factor}. Enter the
          real distance above if you know it.
        </p>
      )}
      <div className="form__actions">
        <button type="button" className="btn btn--primary" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save route"}
        </button>
        <button type="button" className="btn btn--quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/** No map key: pick from the built-in city list, or type any place (then enter the distance by hand). */
function CityPicker({
  reference,
  from,
  to,
  onFrom,
  onTo,
}: {
  reference: TravelReference;
  from: Place;
  to: Place;
  onFrom(p: Place): void;
  onTo(p: Place): void;
}) {
  const options = reference.cities;
  const pick = (name: string): Place => {
    const c = options.find((x) => x.name.toLowerCase() === name.trim().toLowerCase());
    return c ? { name: c.name, lat: c.lat, lng: c.lng } : { name, lat: null, lng: null };
  };
  return (
    <div className="route-editor__grid">
      <label className="filter">
        <span className="filter__label">From</span>
        <input list="bpa-cities" value={from.name} placeholder="City" onChange={(e) => onFrom(pick(e.target.value))} />
      </label>
      <label className="filter">
        <span className="filter__label">To</span>
        <input list="bpa-cities" value={to.name} placeholder="City" onChange={(e) => onTo(pick(e.target.value))} />
      </label>
      <datalist id="bpa-cities">
        {options.map((c) => (
          <option key={c.name} value={c.name} />
        ))}
      </datalist>
    </div>
  );
}

/** With VITE_GOOGLE_MAPS_API_KEY: search or click to set start and finish; Directions gives the road distance. */
function MapPicker({
  from,
  to,
  onFrom,
  onTo,
  onRoute,
}: {
  from: Place;
  to: Place;
  onFrom(p: Place): void;
  onTo(p: Place): void;
  onRoute(km: string | null): void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const fromInput = useRef<HTMLInputElement>(null);
  const toInput = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState("Loading the map…");
  const [active, setActive] = useState<"from" | "to">(from.lat === null ? "from" : "to");
  const activeRef = useRef(active);
  activeRef.current = active;
  const state = useRef<{ g?: Google; map?: Google; renderer?: Google; markers: Google[] }>({ markers: [] });

  useEffect(() => {
    let cancelled = false;
    loadGoogleMaps()
      .then((g) => {
        if (cancelled || !mapEl.current) return;
        const centre = from.lat !== null ? { lat: from.lat, lng: from.lng } : { lat: 31.8, lng: -7.1 };
        const map = new g.maps.Map(mapEl.current, {
          center: centre,
          zoom: from.lat !== null ? 8 : 5,
          mapTypeControl: false,
        });
        const renderer = new g.maps.DirectionsRenderer({ map, suppressMarkers: false });
        state.current = { g, map, renderer, markers: [] };
        const attach = (input: HTMLInputElement | null, set: (p: Place) => void) => {
          if (!input) return;
          const ac = new g.maps.places.Autocomplete(input, { fields: ["geometry", "formatted_address", "name"] });
          ac.addListener("place_changed", () => {
            const p = ac.getPlace();
            const loc = p.geometry?.location;
            if (loc) set({ name: p.formatted_address ?? p.name ?? input.value, lat: loc.lat(), lng: loc.lng() });
          });
        };
        attach(fromInput.current, onFrom);
        attach(toInput.current, onTo);
        const geocoder = new g.maps.Geocoder();
        map.addListener("click", (ev: Google) => {
          const lat = ev.latLng.lat();
          const lng = ev.latLng.lng();
          const set = activeRef.current === "from" ? onFrom : onTo;
          set({ name: `${lat.toFixed(4)}, ${lng.toFixed(4)}`, lat, lng });
          geocoder.geocode({ location: { lat, lng } }, (results: Google[] | null) => {
            if (results?.[0]) set({ name: results[0].formatted_address, lat, lng });
          });
          setActive(activeRef.current === "from" ? "to" : "from");
        });
        setStatus("");
      })
      .catch(() => setStatus("The map couldn't load. Check the Google Maps key, or enter the distance by hand."));
    return () => {
      cancelled = true;
    };
    // Set up once: the inputs and setters stay the same for the editor's lifetime.
  }, []);

  // Recompute the road route whenever both ends are known.
  useEffect(() => {
    const { g, renderer } = state.current;
    if (!g || !renderer || from.lat === null || to.lat === null) return;
    new g.maps.DirectionsService().route(
      {
        origin: { lat: from.lat, lng: from.lng },
        destination: { lat: to.lat, lng: to.lng },
        travelMode: g.maps.TravelMode.DRIVING,
      },
      (result: Google, status: string) => {
        if (status === "OK" && result?.routes?.[0]) {
          renderer.setDirections(result);
          const metres = result.routes[0].legs.reduce((sum: number, leg: Google) => sum + leg.distance.value, 0);
          onRoute((metres / 1000).toFixed(1));
        } else {
          onRoute(null);
          setStatus("No driving route found between these places; the distance will be a straight-line estimate.");
        }
      },
    );
  }, [from.lat, from.lng, to.lat, to.lng, onRoute]);

  return (
    <div className="map-picker">
      <div className="route-editor__grid">
        <label className="filter">
          <span className="filter__label">From</span>
          <input
            ref={fromInput}
            defaultValue={from.name}
            placeholder="Search a place"
            onFocus={() => setActive("from")}
          />
        </label>
        <label className="filter">
          <span className="filter__label">To</span>
          <input ref={toInput} defaultValue={to.name} placeholder="Search a place" onFocus={() => setActive("to")} />
        </label>
      </div>
      <p className="muted route-editor__hint">
        Search above, or click the map to set the {active === "from" ? "start" : "finish"}.
      </p>
      {status && <p className="muted">{status}</p>}
      <div
        ref={mapEl}
        className="map-picker__map"
        role="application"
        aria-label="Map: click to set the start or finish"
      />
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
        {error.includes("Fuel prices") && (
          <Link to="/app/settings" className="no-print">
            Set fuel prices
          </Link>
        )}
      </div>
    );
  }
  if (!estimate) return <p className="muted">Estimating…</p>;

  const c = estimate.currency;
  const low = Number(estimate.cost.low);
  const high = Number(estimate.cost.high);
  const mid = Number(estimate.cost.expected);
  const pos = high > low ? ((mid - low) / (high - low)) * 100 : 50;
  const question = `Explain the fuel cost estimate for the trip "${trip.title}" and how we could reduce it.`;

  return (
    <div className="fuel">
      <div className="fuel__head">
        <div>
          <span className="fuel__label">Estimated fuel cost</span>
          <span className="fuel__value">{formatMoney(estimate.cost.expected, c)}</span>
          <span className="muted">
            likely between {formatMoney(estimate.cost.low, c)} and {formatMoney(estimate.cost.high, c)}
          </span>
        </div>
        <div className="fuel__side">
          <span className="fuel__label">Fuel</span>
          <span>
            {estimate.litres.expected} L {estimate.vehicle.fuel}
          </span>
          <span className="muted">
            {estimate.total_km} km at {estimate.fuel_price.price_per_litre} {c}/L
          </span>
        </div>
      </div>
      <div
        className="fuel__range"
        role="img"
        aria-label={`Range from ${estimate.cost.low} to ${estimate.cost.high} ${c}`}
      >
        <span className="fuel__marker" style={{ left: `${pos}%` }} />
      </div>
      <div className="fuel__range-labels">
        <span>{formatMoney(estimate.cost.low, c)}</span>
        <span>{formatMoney(estimate.cost.high, c)}</span>
      </div>

      <label className="fuel__variance no-print">
        <span className="filter__label">Allow for detours and traffic: {variance}%</span>
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
        <summary>How this is calculated</summary>
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
        Ask the assistant about this
      </Link>
    </div>
  );
}
