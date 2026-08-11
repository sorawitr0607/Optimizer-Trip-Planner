import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  Compass,
  FileSpreadsheet,
  ListChecks,
  MapPinned,
  Languages,
  Route,
  Sparkles,
  SunMoon,
  Wallet,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, rpc, type Journey, type SetupVocabulary, type Trip } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { DeleteTrip } from "../shared/DeleteTrip";
import { useTheme } from "../shared/ThemeProvider";

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
  { x: 70, y: 348, label: "setup" },
  { x: 440, y: 288, label: "places" },
  { x: 790, y: 292, label: "optimize" },
  { x: 1140, y: 258, label: "itinerary" },
] as const;

/** Where each stage's sticker sits, and how far it leans. Tilts are deliberately
 *  uneven — a row of cards at identical angles reads as a grid, not as pinned. */
const STICKERS = [
  { left: 3, top: 62, tilt: -5, depth: 1.1 },
  { left: 5, top: 30, tilt: 4, depth: 0.9 },
  { left: 82, top: 66, tilt: -3, depth: 1.0 },
  { left: 84, top: 26, tilt: 6, depth: 0.8 },
] as const;

const CLOUDS = [
  { key: "a", left: 4, top: 12, width: 190, depth: 0.3, seconds: 68 },
  { key: "b", left: 38, top: 6, width: 250, depth: 0.45, seconds: 84 },
  { key: "c", left: 66, top: 17, width: 160, depth: 0.25, seconds: 58 },
  { key: "d", left: 86, top: 9, width: 210, depth: 0.4, seconds: 76 },
] as const;

const SPARKS = [
  { key: "s1", left: 15, top: 48, delay: 0.2 },
  { key: "s2", left: 22, top: 20, delay: 1.1 },
  { key: "s3", left: 78, top: 46, delay: 0.7 },
  { key: "s4", left: 93, top: 22, delay: 1.6 },
] as const;

const STEPS = [
  [Sparkles, "stage_setup", "landing_how_setup"],
  [MapPinned, "stage_places", "landing_how_places"],
  [Route, "stage_optimize", "landing_how_plan"],
  [ListChecks, "stage_itinerary", "landing_how_use"],
] as const;

export function TripsPage() {
  const { language, setLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
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

  function startPlanning() {
    const form = document.getElementById("start-a-trip");
    if (!form) return;
    form.scrollIntoView({ behavior: "smooth", block: "center" });
    form.classList.remove("is-called");
    // Reading `offsetWidth` restarts the animation; without it a second press does
    // nothing because the class never left.
    void form.offsetWidth;
    form.classList.add("is-called");
    form.querySelector("select")?.focus({ preventScroll: true });
  }

  return (
    <main className="landing">
      {/* Language and theme, before there is a trip to hang a sidebar off.
          They lived only in the shell, so the first screen a Thai-speaking owner
          ever saw was in English with no way to change it until a trip had been
          created — and the theme could not be dimmed before then either. The
          language button is written in the language it switches *to*, which needs
          no translation and is the one label a reader who cannot read the current
          one can still act on. */}
      <div className="landing-controls">
        <button
          aria-label={copy("switch_language", language)}
          onClick={() => setLanguage(language === "en" ? "th" : "en")}
          type="button"
        >
          <Languages aria-hidden="true" size={16} /> {language === "en" ? "ไทย" : "English"}
        </button>
        <button onClick={toggleTheme} type="button">
          <SunMoon aria-hidden="true" size={16} />{" "}
          {copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
        </button>
      </div>
      {/* derives-from: element 5 .hero-content as .landing-hero.

          Built to the reference the owner named: a layered scene with drifting clouds,
          mountains at two depths, a ground plane, sticker cards pinned around a winding
          dotted path, sparkles, and a glowing pill call to action, all moving on
          parallax as the pointer travels.

          **Drawn, not photographed, and that is not a shortcut.** The reference builds
          its hero from 1124 commissioned `.webp` illustrations and animates them with
          framer-motion. Neither is available here: the artwork is someone else's, and
          `WF-034` keeps this app working offline with no remote assets while `WF-026`
          fixes the web runtime at six dependencies. So the *vocabulary* and the
          *motion* are matched in SVG and CSS — including the reference's own
          `glowPulse`, 1.7s ease-in-out infinite, which is the one timing its stylesheet
          states outright.

          The stickers are the four stages, pinned along the route in order, so the
          scene is a picture of the thing this app makes rather than decoration. */}
      <section
        className="landing-hero"
        onPointerMove={(event) => {
          // Parallax without a dependency: one handler writes two custom properties and
          // every layer reads them at its own depth.
          const box = event.currentTarget.getBoundingClientRect();
          const x = (event.clientX - box.left) / box.width - 0.5;
          const y = (event.clientY - box.top) / box.height - 0.5;
          event.currentTarget.style.setProperty("--drift-x", x.toFixed(3));
          event.currentTarget.style.setProperty("--drift-y", y.toFixed(3));
        }}
      >
        <div aria-hidden="true" className="hero-sky">
          {CLOUDS.map((cloud) => (
            <span
              className="hero-cloud"
              key={cloud.key}
              style={{
                left: `${cloud.left}%`,
                top: `${cloud.top}%`,
                ["--depth" as string]: cloud.depth,
                ["--drift-seconds" as string]: `${cloud.seconds}s`,
                width: `${cloud.width}px`,
              }}
            />
          ))}
        </div>

        <div aria-hidden="true" className="hero-scene">
          <svg preserveAspectRatio="none" viewBox="0 0 1200 420">
            <g className="hero-layer hero-layer-far" style={{ ["--depth" as string]: 0.25 }}>
              <path d="M0 214 L150 120 L262 196 L392 96 L520 186 L648 110 L780 198 L906 118 L1040 200 L1200 128 L1200 420 L0 420 Z" />
            </g>
            <g className="hero-layer hero-layer-mid" style={{ ["--depth" as string]: 0.55 }}>
              <path d="M0 268 L160 196 L318 262 L470 178 L640 258 L818 190 L980 264 L1200 200 L1200 420 L0 420 Z" />
            </g>
            <g className="hero-layer hero-layer-near" style={{ ["--depth" as string]: 1 }}>
              <path d="M0 330 L200 300 L420 326 L640 292 L880 324 L1080 296 L1200 320 L1200 420 L0 420 Z" />
              <path className="hero-route" d="M70 348 C 250 300, 320 274, 440 288 S 660 344, 790 292 S 1010 232, 1140 258" fill="none" />
              {STOPS.map((stop, index) => (
                <g className="hero-stop" key={stop.label} style={{ animationDelay: `${1.5 + index * 0.22}s` }} transform={`translate(${stop.x} ${stop.y})`}>
                  <circle className="hero-stop-ring" r="17" />
                  <circle className="hero-stop-dot" r="12" />
                  <text dy="4" textAnchor="middle">{index + 1}</text>
                </g>
              ))}
            </g>
          </svg>
        </div>

        {/* The stickers: one per stage, pinned along the route, tilted and floating. */}
        <div aria-hidden="true" className="hero-stickers">
          {STEPS.map(([Icon, title], index) => (
            <span
              className="hero-sticker"
              key={title}
              style={{
                ["--tilt" as string]: `${STICKERS[index].tilt}deg`,
                ["--depth" as string]: STICKERS[index].depth,
                animationDelay: `${1.7 + index * 0.22}s`,
                left: `${STICKERS[index].left}%`,
                top: `${STICKERS[index].top}%`,
              }}
            >
              <Icon aria-hidden="true" size={17} />
              {copy(title, language)}
            </span>
          ))}
          {SPARKS.map((spark) => (
            <span
              className="hero-spark"
              key={spark.key}
              style={{ animationDelay: `${spark.delay}s`, left: `${spark.left}%`, top: `${spark.top}%` }}
            />
          ))}
        </div>

        <div className="hero-copy">
          <p className="landing-badge">
            <Compass aria-hidden="true" size={15} /> Optimizer Trip Planner
          </p>
          <h1>
            {language === "th"
              ? copy("landing_headline", language)
              : copy("landing_headline", language).split(" ").map((word, index) => (
                  <span className="hero-word" key={`${word}-${index}`} style={{ animationDelay: `${0.09 * index}s` }}>
                    {word}{" "}
                  </span>
                ))}
          </h1>
          <p className="landing-lead">{copy("landing_subtext", language)}</p>
          {/* It was an anchor to `#start` and no element carried that id, so the one
              call to action on the page did nothing at all. It scrolls to the form and
              flashes it now, because arriving at a long page with no idea which of its
              controls you were sent to is barely better than not moving. */}
          <button className="hero-cta" onClick={startPlanning} type="button">
            {copy("start_planning", language)} <ArrowRight aria-hidden="true" size={17} />
          </button>
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
        <form className="stage-card trip-form" id="start-a-trip" onSubmit={submit}>
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
