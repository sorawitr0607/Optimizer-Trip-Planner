import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  Compass,
  FileSpreadsheet,
  ListChecks,
  MapPinned,
  Route,
  Sparkles,
  Wallet,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, rpc, type Journey, type SetupVocabulary, type Trip } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { DeleteTrip } from "../shared/DeleteTrip";

/**
 * The first screen anyone sees, and until now the weakest: a bare heading, two
 * unlabelled text inputs and no statement of what the app is for. It told a
 * first-time owner nothing and asked them to type a destination string blind.
 *
 * Three things changed. The hero says what the app produces before asking for
 * anything. "How it works" names the four stages so the wizard that follows is
 * expected rather than sprung. And the destination is chosen country-then-city
 * from `setup_vocabulary`, which already carries both — the same read the setup
 * form uses, so no method was added.
 *
 * The typed fallback is not optional politeness: `travel_planner/destinations.py`
 * is a picker convenience, and the worldwide-acceptance check requires that a city
 * absent from the table still completes setup. Hence "Another city — type it" on
 * both dropdowns.
 */

/** Sentinel for the typed fallback. Not a country code, so it cannot collide. */
const TYPE_IT = "__type_it__";

// Icons carry no meaning on their own — every one sits beside its own sentence, so a
// screen reader loses nothing by skipping them and they stay `aria-hidden`.
const BULLETS = [
  [MapPinned, "landing_bullet_places"],
  [CalendarClock, "landing_bullet_schedule"],
  [Wallet, "landing_bullet_money"],
  [FileSpreadsheet, "landing_bullet_export"],
] as const;

/** Where the four numbered stops sit on the drawn route. They are the four stages, so
 *  the picture and the "how it works" list below it describe the same journey. */
const STOPS = [
  { x: 80, y: 246, label: "setup" },
  { x: 430, y: 186, label: "places" },
  { x: 760, y: 192, label: "optimize" },
  { x: 1120, y: 158, label: "itinerary" },
] as const;

const STEPS = [
  [Sparkles, "stage_setup", "landing_how_setup"],
  [MapPinned, "stage_places", "landing_how_places"],
  [Route, "stage_optimize", "landing_how_plan"],
  [ListChecks, "stage_itinerary", "landing_how_use"],
] as const;

export function TripsPage() {
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [typedCountry, setTypedCountry] = useState("");
  const [typedCity, setTypedCity] = useState("");

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const vocabulary = useQuery({
    queryKey: ["setup_vocabulary"],
    queryFn: () => rpc<SetupVocabulary>("setup_vocabulary"),
    staleTime: Infinity,
  });

  // The canonical latin name is the stable value on both dropdowns: it becomes the
  // geocoder query, so localizing it would let a language switch change which place
  // is searched. Only the country's *label* is translated.
  const resolvedCountry = country === TYPE_IT ? typedCountry.trim() : country;
  const cities = vocabulary.data?.countries.find((item) => item.code === country)?.cities ?? [];
  const typingCity = country === TYPE_IT || city === TYPE_IT;
  const resolvedCity = typingCity ? typedCity.trim() : city;
  const destination = [resolvedCity, resolvedCountry].filter(Boolean).join(", ");

  const createTrip = useMutation({
    mutationFn: () =>
      rpc<Trip>("create_trip", {
        // A blank name is legal but leaves an unfindable row in the switcher, so the
        // city stands in rather than an empty string.
        name: name.trim() || resolvedCity || destination,
        destination,
        language,
      }),
    onSuccess: async (trip) => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      navigate(`/trips/${trip.trip_id}/setup`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!resolvedCity) return;
    createTrip.mutate();
  }

  const errorCode =
    createTrip.error instanceof ApiError ? createTrip.error.code : createTrip.error?.message;

  return (
    <main className="landing">
      {/* derives-from: element 5 .hero-content as .landing-hero. The donor's dark hero
          is the one element in the catalogue whose job is explaining a product before
          asking for input, which is exactly what was missing here.

          The scene is drawn, not photographed: `WF-034` keeps this app working offline
          with no remote assets, so a stock landscape was never available. Drawing it
          also lets the hero be *about the product* — the dotted route with numbered
          stops is the thing the planner makes, and the four stops are the four stages,
          so the picture and the "how it works" list are the same object. */}
      <section className="landing-hero">
        <div aria-hidden="true" className="hero-scene">
          <svg preserveAspectRatio="none" viewBox="0 0 1200 300">
            <g className="hero-layer hero-layer-far">
              <path d="M0 150 L140 86 L268 142 L392 68 L520 136 L640 80 L764 146 L900 90 L1030 150 L1200 96 L1200 300 L0 300 Z" />
            </g>
            <g className="hero-layer hero-layer-mid">
              <path d="M0 196 L150 148 L300 192 L470 136 L640 188 L820 144 L980 194 L1200 152 L1200 300 L0 300 Z" />
            </g>
            <g className="hero-layer hero-layer-near">
              <path d="M0 244 L200 218 L420 242 L640 214 L880 240 L1080 216 L1200 236 L1200 300 L0 300 Z" />
            </g>
            {/* The route the planner builds, drawing itself left to right. */}
            <path
              className="hero-route"
              d="M80 246 C 240 196, 300 172, 430 186 S 640 246, 760 192 S 980 128, 1120 158"
              fill="none"
            />
            {STOPS.map((stop, index) => (
              <g
                className="hero-stop"
                key={stop.label}
                style={{ animationDelay: `${1.1 + index * 0.28}s` }}
                transform={`translate(${stop.x} ${stop.y})`}
              >
                <circle className="hero-stop-ring" r="19" />
                <circle className="hero-stop-dot" r="14" />
                <text dy="5" textAnchor="middle">{index + 1}</text>
              </g>
            ))}
          </svg>
        </div>

        <div className="hero-copy">
          <p className="landing-badge">
            <Compass aria-hidden="true" size={15} /> Optimizer Trip Planner
          </p>
          {/* Word by word, so the sentence arrives at reading speed rather than all at
              once. Reduced motion turns this into plain text; nothing depends on it. */}
          <h1>
            {copy("landing_headline", language).split(" ").map((word, index) => (
              <span
                className="hero-word"
                key={`${word}-${index}`}
                style={{ animationDelay: `${0.08 * index}s` }}
              >
                {word}{" "}
              </span>
            ))}
          </h1>
          <p className="landing-lead">{copy("landing_subtext", language)}</p>
          <ul className="landing-bullets">
            {BULLETS.map(([Icon, code]) => (
              <li key={code}>
                <span className="landing-bullet-icon">
                  <Icon aria-hidden="true" size={17} />
                </span>
                {copy(code, language)}
              </li>
            ))}
          </ul>
          <p className="landing-note">{copy("landing_local_note", language)}</p>
          <p className="landing-note">{copy("landing_free_note", language)}</p>
        </div>
      </section>

      <div className="landing-columns">
        <div className="landing-main">
          {/* derives-from: element 4 .onboarding-landing-grid as .landing-how */}
          <section className="stage-card landing-how">
            <h2>{copy("landing_how", language)}</h2>
            <ol className="landing-steps">
              {STEPS.map(([Icon, title, detail], index) => (
                <li key={title}>
                  <span className="landing-step-num">{index + 1}</span>
                  <div className="landing-step-body">
                    <strong>
                      <Icon aria-hidden="true" size={16} />
                      {copy(title, language)}
                    </strong>
                    <p>{copy(detail, language)}</p>
                  </div>
                  {index < STEPS.length - 1 ? (
                    <ArrowRight aria-hidden="true" className="landing-step-arrow" size={16} />
                  ) : null}
                </li>
              ))}
            </ol>
          </section>

          <section className="stage-card">
            <h2>{copy("saved_trips", language)}</h2>
            {trips.isPending ? <p>{copy("loading", language)}</p> : null}
            {trips.data?.length === 0 ? (
              <p className="setup-hint">{copy("no_trips_yet", language)}</p>
            ) : null}
            <div className="trip-list">
              {trips.data?.map((trip) => (
                <TripSlot key={trip.trip_id} trip={trip} />
              ))}
            </div>
          </section>
        </div>

        {/* derives-from: element 6 .setup-card as .trip-form */}
        <form className="stage-card trip-form" onSubmit={submit}>
          <h2>{copy("new_trip", language)}</h2>
          <p className="setup-hint">{copy("destination_help", language)}</p>

          <label>
            {copy("country", language)}
            <select
              onChange={(event) => {
                setCountry(event.target.value);
                setCity("");
                setTypedCity("");
              }}
              value={country}
            >
              <option value="">{copy("choose_country", language)}</option>
              {(vocabulary.data?.countries ?? []).map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label[language]}
                </option>
              ))}
              <option value={TYPE_IT}>{copy("type_another_country", language)}</option>
            </select>
          </label>
          {country === TYPE_IT ? (
            <label>
              {copy("country", language)}
              <input
                onChange={(event) => setTypedCountry(event.target.value)}
                placeholder={copy("country_placeholder", language)}
                value={typedCountry}
              />
            </label>
          ) : null}

          <label>
            {copy("city", language)}
            {country && country !== TYPE_IT ? (
              <select onChange={(event) => setCity(event.target.value)} value={city}>
                <option value="">{copy("choose_city", language)}</option>
                {cities.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
                <option value={TYPE_IT}>{copy("type_another_city", language)}</option>
              </select>
            ) : (
              <input
                disabled={!country}
                onChange={(event) => setTypedCity(event.target.value)}
                placeholder={copy("city_placeholder", language)}
                value={typedCity}
              />
            )}
          </label>
          {country && country !== TYPE_IT && city === TYPE_IT ? (
            <label>
              {copy("city", language)}
              <input
                onChange={(event) => setTypedCity(event.target.value)}
                placeholder={copy("city_placeholder", language)}
                value={typedCity}
              />
            </label>
          ) : null}

          <label>
            {copy("name", language)}
            <input
              onChange={(event) => setName(event.target.value)}
              placeholder={resolvedCity || copy("trip_name_placeholder", language)}
              value={name}
            />
          </label>
          <p className="setup-hint">{copy("trip_name_help", language)}</p>

          {destination ? (
            <p className="landing-resolved">
              {copy("destination", language)}: <strong>{destination}</strong>
            </p>
          ) : null}
          {errorCode ? <p className="field-error">⚠ {errorCode}</p> : null}
          <button
            className="setup-primary"
            disabled={!resolvedCity || createTrip.isPending}
            type="submit"
          >
            {copy("start_planning", language)}
          </button>
          {/* A disabled primary action always says why, never falls silent. */}
          {!resolvedCity ? (
            <p className="setup-hint">{copy("destination_required", language)}</p>
          ) : null}
        </form>
      </div>
    </main>
  );
}

/** A saved trip resumes at the stage needing attention, not always at setup, and can
 *  be deleted — see `shared/DeleteTrip.tsx` for why the confirmation is type-the-name. */
function TripSlot({ trip }: { trip: Trip }) {
  const { language } = useLanguage();
  const journey = useQuery({
    queryKey: ["journey", trip.trip_id],
    queryFn: () => rpc<Journey>("journey", { trip_id: trip.trip_id }),
  });
  const stage = journey.data?.next ?? "setup";
  return (
    <div className="trip-slot">
      <Link to={`/trips/${trip.trip_id}/${stage}`}>
        <span className="trip-list-name">
          <strong>{trip.name}</strong>
          <small>{trip.destination}</small>
        </span>
        <span className="trip-list-resume">
          {copy(`stage_${stage}`, language)} → {copy("continue_trip", language)}
        </span>
      </Link>
      <DeleteTrip trip={trip} />
    </div>
  );
}
