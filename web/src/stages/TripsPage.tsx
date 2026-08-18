import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Compass,
  FileSpreadsheet,
  ListChecks,
  MapPinned,
  Languages,
  Route,
  ShieldCheck,
  Sparkles,
  SunMoon,
  Timer,
  Utensils,
  Wallet,
  XCircle,
  Zap,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, rpc, type Journey, type SetupVocabulary, type Trip } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { DeleteTrip } from "../shared/DeleteTrip";
import { useTheme } from "../shared/ThemeProvider";

/** Sentinel for the typed fallback. Not a country code, so it cannot collide. */
const TYPE_IT = "__type_it__";

const BULLETS = [
  [MapPinned, "landing_bullet_places"],
  [CalendarClock, "landing_bullet_schedule"],
  [Wallet, "landing_bullet_money"],
  [FileSpreadsheet, "landing_bullet_export"],
] as const;

const CLOUDS = [
  { key: "a", left: 4, top: 12, width: 190, depth: 0.3, seconds: 68 },
  { key: "b", left: 38, top: 6, width: 250, depth: 0.45, seconds: 84 },
  { key: "c", left: 66, top: 17, width: 160, depth: 0.25, seconds: 58 },
  { key: "d", left: 86, top: 9, width: 210, depth: 0.4, seconds: 76 },
] as const;

const SPARKS = [
  { key: "s1", left: 12, top: 44, delay: 0.2 },
  { key: "s2", left: 24, top: 18, delay: 1.1 },
  { key: "s3", left: 74, top: 42, delay: 0.7 },
  { key: "s4", left: 91, top: 20, delay: 1.6 },
] as const;

const STEPS = [
  [Sparkles, "stage_setup", "landing_how_setup"],
  [MapPinned, "stage_places", "landing_how_places"],
  [Route, "stage_optimize", "landing_how_plan"],
  [ListChecks, "stage_itinerary", "landing_how_use"],
] as const;

const DEMO_DESTINATIONS = [
  {
    id: "porto",
    city: "Porto, Portugal",
    badge: "Culture & River",
    rows: [
      { time: "10:21", name: "House of Filigree", kind: "visit" },
      { leg: "7 min walk (450m)" },
      { time: "11:51", name: "Lunch near Ribeira", kind: "meal" },
      { leg: "13 min walk (800m)" },
      { time: "13:08", name: "Arqueossítio da Rua de Dom Hugo", kind: "visit" },
      { leg: "10 min walk (600m)" },
      { time: "14:39", name: "Jardim de S. Lázaro", kind: "visit" },
      { time: "17:30", name: "Dinner on the evening route", kind: "meal" },
    ],
  },
  {
    id: "taipei",
    city: "Taipei, Taiwan",
    badge: "Food & Temples",
    rows: [
      { time: "09:30", name: "Longshan Temple", kind: "visit" },
      { leg: "9 min walk (550m)" },
      { time: "10:45", name: "Bopiliao Historic Block", kind: "visit" },
      { leg: "14 min walk (900m)" },
      { time: "12:00", name: "Yongkang Beef Noodles", kind: "meal" },
      { leg: "12 min walk (750m)" },
      { time: "14:15", name: "Chiang Kai-shek Memorial Hall", kind: "visit" },
      { time: "18:00", name: "Raohe Night Market Marathon", kind: "meal" },
    ],
  },
  {
    id: "tokyo",
    city: "Tokyo, Japan",
    badge: "Shrines & Parks",
    rows: [
      { time: "09:00", name: "Meiji Jingu Shrine", kind: "visit" },
      { leg: "11 min walk (700m)" },
      { time: "10:30", name: "Yoyogi Park Walking Loop", kind: "visit" },
      { leg: "15 min walk (950m)" },
      { time: "12:00", name: "Harajuku Gourmet Lunch", kind: "meal" },
      { leg: "10 min walk (620m)" },
      { time: "13:45", name: "Nezu Museum & Japanese Garden", kind: "visit" },
      { time: "17:45", name: "Shibuya Sky & Evening Route", kind: "meal" },
    ],
  },
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
  const [activeDemo, setActiveDemo] = useState<"porto" | "taipei" | "tokyo">("porto");
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const vocabulary = useQuery({
    queryKey: ["setup_vocabulary"],
    queryFn: () => rpc<SetupVocabulary>("setup_vocabulary"),
    staleTime: Infinity,
  });

  const resolvedCountry = country === TYPE_IT ? typedCountry.trim() : country;
  const cities = vocabulary.data?.countries.find((item) => item.code === country)?.cities ?? [];
  const typingCity = country === TYPE_IT || city === TYPE_IT;
  const resolvedCity = typingCity ? typedCity.trim() : city;
  const destination = [resolvedCity, resolvedCountry].filter(Boolean).join(", ");

  const createTrip = useMutation({
    mutationFn: () =>
      rpc<Trip>("create_trip", {
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
    void form.offsetWidth;
    form.classList.add("is-called");
    form.querySelector("select")?.focus({ preventScroll: true });
  }

  const currentDemo = DEMO_DESTINATIONS.find((d) => d.id === activeDemo) ?? DEMO_DESTINATIONS[0];

  return (
    // derives-from: element 5 .hero-content as .landing-hero
    <main className="landing">
      {/* Navigation & Utilities Header */}
      <nav aria-label="Landing Navigation" className="landing-nav">
        <div className="landing-nav-brand">
          <Compass aria-hidden="true" size={18} />
          <strong>Optimizer Trip Planner</strong>
        </div>
        <div className="landing-nav-links">
          <a href="#solutions">{copy("landing_solutions_badge", language)}</a>
          <a href="#showcase">{copy("landing_showcase_badge", language)}</a>
          <a href="#comparison">{copy("landing_comparison_badge", language)}</a>
          <a href="#faq">{copy("landing_faq_badge", language)}</a>
        </div>
        <div className="landing-controls">
          <button
            aria-label={copy("switch_language", language)}
            onClick={() => setLanguage(language === "en" ? "th" : "en")}
            type="button"
          >
            <Languages aria-hidden="true" size={15} /> {language === "en" ? "ไทย" : "English"}
          </button>
          <button onClick={toggleTheme} type="button">
            <SunMoon aria-hidden="true" size={15} />{" "}
            {copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
          </button>
        </div>
      </nav>

      {/* SECTION 1: HERO (Above the Fold) */}
      <section
        className="landing-hero"
        onPointerMove={(event) => {
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
            </g>
          </svg>
        </div>

        <div aria-hidden="true" className="hero-stickers">
          {SPARKS.map((spark) => (
            <span
              className="hero-spark"
              key={spark.key}
              style={{ animationDelay: `${spark.delay}s`, left: `${spark.left}%`, top: `${spark.top}%` }}
            />
          ))}
        </div>

        {/* Hero Left Column: Copy & High-Impact Value Prop */}
        <div className="hero-copy">
          <div className="hero-badges-row">
            <span className="landing-badge">
              <Zap aria-hidden="true" size={14} /> {copy("landing_tagline", language)}
            </span>
            <span className="hero-mini-pill">
              <ShieldCheck aria-hidden="true" size={13} /> {copy("landing_pill_offline", language)}
            </span>
          </div>

          <h1>
            {language === "th"
              ? copy("landing_headline", language)
              : copy("landing_headline", language).split(" ").map((word, index) => (
                  <span className="hero-word" key={`${word}-${index}`} style={{ animationDelay: `${0.08 * index}s` }}>
                    {word}{" "}
                  </span>
                ))}
          </h1>

          <p className="landing-lead">{copy("landing_subtext", language)}</p>

          <div className="hero-cta-wrap">
            <button className="hero-cta" onClick={startPlanning} type="button">
              {copy("start_planning", language)} <ArrowRight aria-hidden="true" size={17} />
            </button>
            <p className="hero-trust-note">{copy("landing_hero_trust_badge", language)}</p>
          </div>

          {/* Floating Feature Tags in Hero */}
          <div className="hero-tags-strip">
            <span className="hero-tag-item">
              <Sparkles aria-hidden="true" size={13} /> {copy("landing_pill_solver", language)}
            </span>
            <span className="hero-tag-item">
              <Timer aria-hidden="true" size={13} /> {copy("landing_pill_walking", language)}
            </span>
            <span className="hero-tag-item">
              <CheckCircle2 aria-hidden="true" size={13} /> {copy("landing_pill_nosignup", language)}
            </span>
          </div>
        </div>

        {/* Hero Right Column: Interactive Product Demo Card */}
        <div className="hero-demo">
          <div className="hero-demo-card">
            <div className="hero-demo-tabs">
              {DEMO_DESTINATIONS.map((dest) => (
                <button
                  className={`hero-demo-tab ${activeDemo === dest.id ? "active" : ""}`}
                  key={dest.id}
                  onClick={() => setActiveDemo(dest.id as "porto" | "taipei" | "tokyo")}
                  type="button"
                >
                  {dest.city.split(",")[0]}
                </button>
              ))}
            </div>

            <div className="hero-demo-head">
              <span>{currentDemo.city}</span>
              <span className="hero-demo-badge">{currentDemo.badge}</span>
            </div>

            <ol className="hero-demo-rows">
              {currentDemo.rows.map((row, index) =>
                "leg" in row ? (
                  <li className="hero-demo-leg" key={`leg-${index}`}>
                    <span>{row.leg}</span>
                  </li>
                ) : (
                  <li className={`hero-demo-row ${row.kind}`} key={row.name}>
                    <time>{row.time}</time>
                    <span className="hero-demo-name">{row.name}</span>
                    {row.kind === "meal" ? <Utensils aria-hidden="true" size={12} /> : null}
                  </li>
                ),
              )}
            </ol>

            <div className="hero-demo-footer">
              <span>✓ {copy("landing_bullet_schedule", language)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 2: SOLUTIONS & BENEFITS ("So What?" 3-Card Layout) */}
      <section className="landing-section" id="solutions">
        <div className="section-header">
          <span className="section-badge">{copy("landing_solutions_badge", language)}</span>
          <h2>{copy("landing_solutions_title", language)}</h2>
          <p className="section-lead">{copy("landing_solutions_lead", language)}</p>
        </div>

        <div className="benefits-grid">
          <div className="benefit-card">
            <div className="benefit-icon-box">
              <CalendarClock aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_1_title", language)}</h3>
            <p>{copy("landing_benefit_1_desc", language)}</p>
          </div>

          <div className="benefit-card">
            <div className="benefit-icon-box">
              <Timer aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_2_title", language)}</h3>
            <p>{copy("landing_benefit_2_desc", language)}</p>
          </div>

          <div className="benefit-card">
            <div className="benefit-icon-box">
              <Wallet aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_3_title", language)}</h3>
            <p>{copy("landing_benefit_3_desc", language)}</p>
          </div>
        </div>
      </section>

      {/* SECTION 3: PRODUCT DEMO SHOWCASE ("Show, Don't Tell" Walkthrough) */}
      <section className="landing-section showcase-section" id="showcase">
        <div className="section-header">
          <span className="section-badge">{copy("landing_showcase_badge", language)}</span>
          <h2>{copy("landing_showcase_title", language)}</h2>
          <p className="section-lead">{copy("landing_showcase_lead", language)}</p>
        </div>

        <ol className="showcase-steps-grid">
          {STEPS.map(([Icon, title, detail], index) => (
            <li className="showcase-step-card" key={title}>
              <div className="showcase-step-header">
                <span className="showcase-step-num">{index + 1}</span>
                <span className="showcase-step-icon">
                  <Icon aria-hidden="true" size={18} />
                </span>
              </div>
              <h4>{copy(title, language)}</h4>
              <p>{copy(detail, language)}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* SECTION 4: SOCIAL PROOF & GROUND TRUTH CREDIBILITY */}
      <section className="landing-section credibility-section">
        <div className="section-header">
          <span className="section-badge">{copy("landing_proof_badge", language)}</span>
          <h2>{copy("landing_proof_title", language)}</h2>
        </div>

        <div className="credibility-grid">
          <div className="credibility-stat-card">
            <span className="stat-number">512+</span>
            <span className="stat-label">{copy("landing_proof_tests", language)}</span>
          </div>
          <div className="credibility-stat-card">
            <span className="stat-number">13</span>
            <span className="stat-label">{copy("landing_proof_destinations", language)}</span>
          </div>
          <div className="credibility-stat-card">
            <span className="stat-number">6-Sheet</span>
            <span className="stat-label">{copy("landing_proof_export", language)}</span>
          </div>
          <div className="credibility-stat-card">
            <span className="stat-number">100%</span>
            <span className="stat-label">{copy("landing_proof_privacy", language)}</span>
          </div>
        </div>

        <div className="landing-trust-strip">
          <ul className="landing-bullets">
            {BULLETS.map(([Icon, code]) => (
              <li key={code}>
                <span className="landing-bullet-icon">
                  <Icon aria-hidden="true" size={16} />
                </span>
                {copy(code, language)}
              </li>
            ))}
          </ul>
          <p className="landing-note">{copy("landing_local_note", language)}</p>
          <p className="landing-note">{copy("landing_free_note", language)}</p>
        </div>
      </section>

      {/* SECTION 5: WHY US? (Side-by-Side Comparison Table) */}
      <section className="landing-section comparison-section" id="comparison">
        <div className="section-header">
          <span className="section-badge">{copy("landing_comparison_badge", language)}</span>
          <h2>{copy("landing_comparison_title", language)}</h2>
        </div>

        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>{copy("landing_comparison_col_feature", language)}</th>
                <th>{copy("landing_comparison_col_generic", language)}</th>
                <th className="highlight-col">{copy("landing_comparison_col_optimizer", language)}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row1_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} /> {copy("landing_comp_row1_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} /> {copy("landing_comp_row1_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row2_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} /> {copy("landing_comp_row2_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} /> {copy("landing_comp_row2_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row3_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} /> {copy("landing_comp_row3_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} /> {copy("landing_comp_row3_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row4_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} /> {copy("landing_comp_row4_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} /> {copy("landing_comp_row4_good", language)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION 6: HIGH-CONVERSION CTA & WORKING TRIP WORKSPACE */}
      <section className="landing-section action-workspace-section" id="start-planning">
        <div className="section-header">
          <h2>{copy("landing_cta_section_title", language)}</h2>
          <p className="section-lead">{copy("landing_cta_section_lead", language)}</p>
        </div>

        <div className="landing-columns">
          <div className="landing-main">
            {/* Saved Trips Manager */}
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

          {/* New Trip Creation Form */}
          <form className="stage-card trip-form" id="start-a-trip" onSubmit={submit}>
            <h2>{copy("new_trip", language)}</h2>
            <p className="setup-hint" id="destination-help">
              {copy("destination_help", language)}
            </p>

            <label>
              <span>
                {copy("country", language)}
                <span aria-hidden="true" className="setup-required">*</span>
                <span className="setup-hint"> {copy("required_field", language)}</span>
              </span>
              <select
                aria-describedby="destination-help"
                name="country"
                onChange={(event) => {
                  setCountry(event.target.value);
                  setCity("");
                  setTypedCity("");
                }}
                required
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
                <span>
                  {copy("country", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  autoCapitalize="words"
                  autoComplete="country-name"
                  autoCorrect="off"
                  name="country-custom"
                  onChange={(event) => setTypedCountry(event.target.value)}
                  placeholder={copy("country_placeholder", language)}
                  required
                  spellCheck={false}
                  type="text"
                  value={typedCountry}
                />
              </label>
            ) : null}

            <label>
              <span>
                {copy("city", language)}
                <span aria-hidden="true" className="setup-required">*</span>
                <span className="setup-hint"> {copy("required_field", language)}</span>
              </span>
              {country && country !== TYPE_IT ? (
                <select
                  aria-describedby="destination-help"
                  name="city"
                  onChange={(event) => setCity(event.target.value)}
                  required
                  value={city}
                >
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
                  autoCapitalize="words"
                  autoComplete="off"
                  autoCorrect="off"
                  disabled={!country}
                  name="city-custom"
                  onChange={(event) => setTypedCity(event.target.value)}
                  placeholder={copy("city_placeholder", language)}
                  required={Boolean(country)}
                  spellCheck={false}
                  type="text"
                  value={typedCity}
                />
              )}
            </label>
            {country && country !== TYPE_IT && city === TYPE_IT ? (
              <label>
                <span>
                  {copy("city", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  autoCapitalize="words"
                  autoComplete="off"
                  autoCorrect="off"
                  name="city-custom"
                  onChange={(event) => setTypedCity(event.target.value)}
                  placeholder={copy("city_placeholder", language)}
                  required
                  spellCheck={false}
                  type="text"
                  value={typedCity}
                />
              </label>
            ) : null}

            <label>
              {copy("trip_name", language)}
              <input
                aria-describedby="trip-name-help"
                autoCapitalize="sentences"
                autoComplete="off"
                name="trip-name"
                onChange={(event) => setName(event.target.value)}
                placeholder={resolvedCity || copy("trip_name_placeholder", language)}
                type="text"
                value={name}
              />
            </label>
            <p className="setup-hint" id="trip-name-help">
              {copy("trip_name_help", language)}
            </p>

            {destination ? (
              <p className="landing-resolved">
                {copy("destination", language)}: <strong>{destination}</strong>
              </p>
            ) : null}
            {errorCode ? <p className="field-error">⚠ {errorCode}</p> : null}
            <button
              aria-describedby={!resolvedCity ? "destination-required" : undefined}
              className="setup-primary"
              disabled={!resolvedCity || createTrip.isPending}
              type="submit"
            >
              {copy("start_planning", language)}
            </button>
            {!resolvedCity ? (
              <p className="setup-hint" id="destination-required">
                {copy("destination_required", language)}
              </p>
            ) : null}
          </form>
        </div>
      </section>

      {/* SECTION 7: FAQ & OBJECTION HANDLING */}
      <section className="landing-section faq-section" id="faq">
        <div className="section-header">
          <span className="section-badge">{copy("landing_faq_badge", language)}</span>
          <h2>{copy("landing_faq_title", language)}</h2>
        </div>

        <div className="faq-list">
          {[1, 2, 3, 4, 5].map((num, index) => (
            <div
              className={`faq-item ${openFaq === index ? "open" : ""}`}
              key={num}
            >
              <button
                aria-expanded={openFaq === index}
                className="faq-question"
                onClick={() => setOpenFaq(openFaq === index ? null : index)}
                type="button"
              >
                <span>{copy(`landing_faq_q${num}`, language)}</span>
                <ChevronDown aria-hidden="true" className="faq-chevron" size={18} />
              </button>
              {openFaq === index ? (
                <div className="faq-answer">
                  <p>{copy(`landing_faq_a${num}`, language)}</p>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="footer-left">
            <Compass aria-hidden="true" size={18} />
            <span>Optimizer Trip Planner · MIT Open Source</span>
          </div>
          <div className="footer-right">
            <span>© OpenStreetMap contributors (ODbL)</span>
          </div>
        </div>
      </footer>
    </main>
  );
}

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
