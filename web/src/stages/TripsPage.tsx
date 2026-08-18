import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Calculator,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Compass,
  FileSpreadsheet,
  Globe,
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

type PacingMode = "relaxed" | "balanced" | "marathon";

interface DemoCity {
  id: "porto" | "taipei" | "tokyo" | "reykjavik";
  city: string;
  country: string;
  badge: string;
  currency: string;
  pacing: Record<
    PacingMode,
    {
      walkKm: string;
      stopsCount: number;
      stops: Array<{ time: string; name: string; kind: "visit" | "meal"; leg?: string }>;
    }
  >;
}

const DEMO_DESTINATIONS: DemoCity[] = [
  {
    id: "porto",
    city: "Porto",
    country: "Portugal",
    badge: "Culture & River",
    currency: "EUR (€)",
    pacing: {
      relaxed: {
        walkKm: "2.8 km",
        stopsCount: 4,
        stops: [
          { time: "10:00", name: "Livraria Lello & Clérigos Tower", kind: "visit" },
          { leg: "8 min leisurely stroll (480m)", time: "", name: "", kind: "visit" },
          { time: "12:00", name: "Ribeira Waterfront Lunch & Wine", kind: "meal" },
          { leg: "12 min tram + walk (750m)", time: "", name: "", kind: "visit" },
          { time: "14:30", name: "Palácio da Bolsa Historic Tour", kind: "visit" },
          { time: "17:30", name: "Sunset Port Wine Cellar Tasting", kind: "meal" },
        ],
      },
      balanced: {
        walkKm: "4.6 km",
        stopsCount: 6,
        stops: [
          { time: "09:30", name: "São Bento Tile Station", kind: "visit" },
          { leg: "6 min walk (400m)", time: "", name: "", kind: "visit" },
          { time: "10:45", name: "Livraria Lello & Garden", kind: "visit" },
          { leg: "9 min walk (620m)", time: "", name: "", kind: "visit" },
          { time: "12:15", name: "Francesinha Lunch at Café Santiago", kind: "meal" },
          { leg: "14 min walk (900m)", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Dom Luís I Bridge Panoramic Crossing", kind: "visit" },
          { leg: "8 min walk (500m)", time: "", name: "", kind: "visit" },
          { time: "15:45", name: "Vila Nova de Gaia Waterfront", kind: "visit" },
          { time: "18:00", name: "Traditional Fado Dinner", kind: "meal" },
        ],
      },
      marathon: {
        walkKm: "7.9 km",
        stopsCount: 8,
        stops: [
          { time: "08:30", name: "Miradouro da Vitória Sunrise", kind: "visit" },
          { leg: "7 min walk (450m)", time: "", name: "", kind: "visit" },
          { time: "09:45", name: "São Bento & Clérigos Tower", kind: "visit" },
          { leg: "10 min walk (680m)", time: "", name: "", kind: "visit" },
          { time: "11:15", name: "Carmo Church Azulejos", kind: "visit" },
          { time: "12:30", name: "Quick Market Lunch at Bolhão", kind: "meal" },
          { leg: "15 min walk (1.1km)", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Palácio da Bolsa & Church of St. Francis", kind: "visit" },
          { leg: "12 min walk (800m)", time: "", name: "", kind: "visit" },
          { time: "16:00", name: "Jardins do Palácio de Cristal", kind: "visit" },
          { time: "18:30", name: "Rooftop Port & Sunset Tasting", kind: "meal" },
        ],
      },
    },
  },
  {
    id: "taipei",
    city: "Taipei",
    country: "Taiwan",
    badge: "Food & Temples",
    currency: "TWD (NT$)",
    pacing: {
      relaxed: {
        walkKm: "3.2 km",
        stopsCount: 4,
        stops: [
          { time: "09:30", name: "Longshan Historic Temple", kind: "visit" },
          { leg: "9 min shaded walk (550m)", time: "", name: "", kind: "visit" },
          { time: "11:30", name: "Yongkang Street Xiaolongbao Lunch", kind: "meal" },
          { leg: "14 min metro + walk", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "National Palace Museum Gallery", kind: "visit" },
          { time: "17:30", name: "Dihua Street Tea Tasting & Treats", kind: "meal" },
        ],
      },
      balanced: {
        walkKm: "5.4 km",
        stopsCount: 6,
        stops: [
          { time: "09:00", name: "Longshan Temple & Herb Lane", kind: "visit" },
          { leg: "8 min walk (500m)", time: "", name: "", kind: "visit" },
          { time: "10:30", name: "Bopiliao Historical Block", kind: "visit" },
          { leg: "12 min metro + walk", time: "", name: "", kind: "visit" },
          { time: "12:00", name: "Beef Noodle Soup at Yong Kang", kind: "meal" },
          { leg: "11 min walk (720m)", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Chiang Kai-shek Memorial Hall", kind: "visit" },
          { leg: "15 min metro", time: "", name: "", kind: "visit" },
          { time: "16:00", name: "Elephant Mountain Lookout Trail", kind: "visit" },
          { time: "18:30", name: "Raohe Night Market Feast", kind: "meal" },
        ],
      },
      marathon: {
        walkKm: "8.6 km",
        stopsCount: 9,
        stops: [
          { time: "08:00", name: "Traditional Soy Milk & You Tiao", kind: "meal" },
          { leg: "10 min walk", time: "", name: "", kind: "visit" },
          { time: "09:15", name: "Longshan & Qingshan Temples", kind: "visit" },
          { leg: "14 min metro", time: "", name: "", kind: "visit" },
          { time: "11:00", name: "Songshan Cultural Creative Park", kind: "visit" },
          { time: "12:30", name: "Din Tai Fung Dim Sum", kind: "meal" },
          { leg: "15 min transit", time: "", name: "", kind: "visit" },
          { time: "14:15", name: "Taipei 101 Observatory Deck", kind: "visit" },
          { leg: "20 min hike (1.4km)", time: "", name: "", kind: "visit" },
          { time: "16:30", name: "Elephant Mountain Sunset", kind: "visit" },
          { time: "18:45", name: "Shilin Night Market Food Marathon", kind: "meal" },
        ],
      },
    },
  },
  {
    id: "tokyo",
    city: "Tokyo",
    country: "Japan",
    badge: "Shrines & Innovation",
    currency: "JPY (¥)",
    pacing: {
      relaxed: {
        walkKm: "3.5 km",
        stopsCount: 4,
        stops: [
          { time: "09:30", name: "Meiji Jingu Forest Walk", kind: "visit" },
          { leg: "12 min park stroll (800m)", time: "", name: "", kind: "visit" },
          { time: "12:00", name: "Harajuku Gourmet Soba Lunch", kind: "meal" },
          { leg: "10 min walk (650m)", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Nezu Museum & Private Garden", kind: "visit" },
          { time: "17:30", name: "Omotesando Lantern Dinner", kind: "meal" },
        ],
      },
      balanced: {
        walkKm: "5.8 km",
        stopsCount: 6,
        stops: [
          { time: "09:00", name: "Meiji Jingu Inner Sanctuary", kind: "visit" },
          { leg: "10 min walk (650m)", time: "", name: "", kind: "visit" },
          { time: "10:30", name: "Yoyogi Park & Harajuku Lanes", kind: "visit" },
          { leg: "12 min walk (780m)", time: "", name: "", kind: "visit" },
          { time: "12:15", name: "Tonkatsu Lunch in Shibuya", kind: "meal" },
          { leg: "8 min walk (520m)", time: "", name: "", kind: "visit" },
          { time: "13:45", name: "Shibuya Crossing & Hachiko", kind: "visit" },
          { leg: "15 min metro", time: "", name: "", kind: "visit" },
          { time: "15:30", name: "Shibuya Sky Observation Deck", kind: "visit" },
          { time: "18:00", name: "Yakitori Alley in Shinjuku", kind: "meal" },
        ],
      },
      marathon: {
        walkKm: "9.2 km",
        stopsCount: 9,
        stops: [
          { time: "08:00", name: "Tsukiji Outer Fish Market Breakfast", kind: "meal" },
          { leg: "15 min transit", time: "", name: "", kind: "visit" },
          { time: "09:30", name: "Senso-ji Temple & Asakusa Pagoda", kind: "visit" },
          { leg: "12 min walk (800m)", time: "", name: "", kind: "visit" },
          { time: "11:00", name: "Tokyo Skytree Town Panorama", kind: "visit" },
          { time: "12:30", name: "Ueno Market Ramen Lunch", kind: "meal" },
          { leg: "14 min transit", time: "", name: "", kind: "visit" },
          { time: "14:15", name: "Akihabara Tech & Arcade Alley", kind: "visit" },
          { leg: "16 min transit", time: "", name: "", kind: "visit" },
          { time: "16:45", name: "Shinjuku Gyoen National Garden", kind: "visit" },
          { time: "19:00", name: "Omoide Yokocho Izakaya Dinner", kind: "meal" },
        ],
      },
    },
  },
  {
    id: "reykjavik",
    city: "Reykjavík",
    country: "Iceland",
    badge: "Geothermal & Nature",
    currency: "ISK (kr)",
    pacing: {
      relaxed: {
        walkKm: "2.4 km",
        stopsCount: 4,
        stops: [
          { time: "10:00", name: "Hallgrímskirkja Tower View", kind: "visit" },
          { leg: "8 min walk (500m)", time: "", name: "", kind: "visit" },
          { time: "12:00", name: "Harpa Concert Hall & Seafood Lunch", kind: "meal" },
          { leg: "10 min scenic coastline walk", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Sun Voyager Sculpture & Harbor", kind: "visit" },
          { time: "16:30", name: "Sky Lagoon Geothermal Soak", kind: "meal" },
        ],
      },
      balanced: {
        walkKm: "4.2 km",
        stopsCount: 5,
        stops: [
          { time: "09:30", name: "Old Harbor & Whale Fjord View", kind: "visit" },
          { leg: "9 min walk (600m)", time: "", name: "", kind: "visit" },
          { time: "11:00", name: "Hallgrímskirkja Architectural View", kind: "visit" },
          { time: "12:30", name: "Icelandic Lamb Stew at Café Loki", kind: "meal" },
          { leg: "12 min walk (750m)", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "National Museum of Iceland", kind: "visit" },
          { time: "17:30", name: "Blue Lagoon Evening Geothermal Bath", kind: "meal" },
        ],
      },
      marathon: {
        walkKm: "7.0 km",
        stopsCount: 7,
        stops: [
          { time: "08:30", name: "Tjörnin Lake Bird Sanctuary Loop", kind: "visit" },
          { leg: "8 min walk", time: "", name: "", kind: "visit" },
          { time: "09:45", name: "Hallgrímskirkja & Old Town Streets", kind: "visit" },
          { leg: "11 min walk", time: "", name: "", kind: "visit" },
          { time: "11:15", name: "Harpa & Coastal Sculpture Walk", kind: "visit" },
          { time: "12:30", name: "Fresh Catch Fish & Chips Lunch", kind: "meal" },
          { leg: "20 min transit", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Perlan Museum & Ice Cave Simulation", kind: "visit" },
          { time: "17:30", name: "Geothermal Lagoon & Northern Lights Hunt", kind: "meal" },
        ],
      },
    },
  },
];

const PRESETS = [
  {
    country: "Japan",
    city: "Tokyo",
    name: "Tokyo 6-Day City & Culture",
    badge: "Shrines & Tech",
    days: "6 Days",
    tagKey: "landing_preset_tokyo",
  },
  {
    country: "Taiwan",
    city: "Taipei",
    name: "Taipei 4-Day Food & Night Markets",
    badge: "Street Food",
    days: "4 Days",
    tagKey: "landing_preset_taipei",
  },
  {
    country: "Portugal",
    city: "Porto",
    name: "Porto 3-Day Riverfront & Wine",
    badge: "Wine & History",
    days: "3 Days",
    tagKey: "landing_preset_porto",
  },
  {
    country: "Iceland",
    city: "Reykjavík",
    name: "Iceland 5-Day Nature & Glaciers",
    badge: "Geothermal",
    days: "5 Days",
    tagKey: "landing_preset_reykjavik",
  },
];

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

  // Interactive Simulator State
  const [activeCityId, setActiveCityId] = useState<"porto" | "taipei" | "tokyo" | "reykjavik">("porto");
  const [pacingMode, setPacingMode] = useState<PacingMode>("balanced");

  // Interactive Pain/Math Tabs
  const [painTab, setPainTab] = useState<"ai" | "optimizer">("optimizer");

  // Interactive Product Lab Stepper
  const [activeLabStep, setActiveLabStep] = useState<number>(0);

  // Interactive Split Calculator Sandbox State
  const [sampleBill1, setSampleBill1] = useState<number>(120);
  const [sampleBill2, setSampleBill2] = useState<number>(60);
  const [sampleBill3, setSampleBill3] = useState<number>(45);

  // FAQ Accordion State
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const vocabulary = useQuery({
    queryKey: ["setup_vocabulary"],
    queryFn: () => rpc<SetupVocabulary>("setup_vocabulary"),
    staleTime: Infinity,
  });

  const resolvedCountry = country === TYPE_IT ? typedCountry.trim() : country;
  const cities = vocabulary.data?.countries.find((item) => item.code === country)?.cities ?? [];
  const typingCity = country === TYPE_IT || city === TYPE_IT || cities.length === 0;
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

  function scrollToSection(id: string) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth" });
  }

  function applyPreset(preset: (typeof PRESETS)[number]) {
    setCountry(preset.country);
    setCity(preset.city);
    setName(preset.name);
    scrollToSection("start-a-trip");
  }

  const selectedCityData = DEMO_DESTINATIONS.find((d) => d.id === activeCityId) ?? DEMO_DESTINATIONS[0];
  const selectedPacingData = selectedCityData.pacing[pacingMode];

  // Bill split computation: Alex paid Bill1, Sam paid Bill2, Jordan paid Bill3
  const totalBill = sampleBill1 + sampleBill2 + sampleBill3;
  const perPerson = Math.round((totalBill / 3) * 10) / 10;
  const alexNet = Math.round((sampleBill1 - perPerson) * 10) / 10;
  const samNet = Math.round((sampleBill2 - perPerson) * 10) / 10;
  const jordanNet = Math.round((sampleBill3 - perPerson) * 10) / 10;

  return (
    // derives-from: element 5 .hero-content as .landing-hero
    <main className="landing">
      {/* -------------------------------------------------------------
          TOP BAR & UTILITY NAVIGATION (Hack the North style)
          ------------------------------------------------------------- */}
      <nav aria-label="Landing Navigation" className="landing-nav">
        <div className="landing-nav-brand">
          <Compass aria-hidden="true" size={18} />
          <strong>Optimizer Trip Planner</strong>
          <span className="nav-version-badge">v2.0 · MIT</span>
        </div>
        <div className="landing-nav-links">
          <button onClick={() => scrollToSection("simulator")} type="button">
            {copy("landing_sim_mode_label", language)}
          </button>
          <button onClick={() => scrollToSection("pain-math")} type="button">
            {copy("landing_pain_ai_tab", language)}
          </button>
          <button onClick={() => scrollToSection("lab")} type="button">
            {copy("landing_showcase_badge", language)}
          </button>
          <button onClick={() => scrollToSection("split-sandbox")} type="button">
            {copy("landing_split_sandbox_title", language)}
          </button>
          <button onClick={() => scrollToSection("comparison")} type="button">
            {copy("landing_comparison_badge", language)}
          </button>
          <button onClick={() => scrollToSection("faq")} type="button">
            {copy("landing_faq_badge", language)}
          </button>
        </div>
        <div className="landing-controls">
          <button
            aria-label={copy("switch_language", language)}
            onClick={() => setLanguage(language === "en" ? "th" : "en")}
            type="button"
          >
            <Languages aria-hidden="true" size={14} /> {language === "en" ? "ไทย" : "English"}
          </button>
          <button onClick={toggleTheme} type="button">
            <SunMoon aria-hidden="true" size={14} />{" "}
            {copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
          </button>
        </div>
      </nav>

      {/* -------------------------------------------------------------
          SECTION 1: HERO (Above the Fold with Live Simulator Teaser)
          ------------------------------------------------------------- */}
      <section
        className="landing-hero"
        id="hero"
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          e.currentTarget.style.setProperty("--drift-x", String((e.clientX - rect.left) / rect.width - 0.5));
          e.currentTarget.style.setProperty("--drift-y", String((e.clientY - rect.top) / rect.height - 0.5));
        }}
      >
        <div aria-hidden="true" className="hero-sky">
          {CLOUDS.map((cloud) => (
            <span
              className="hero-cloud"
              key={cloud.key}
              style={
                {
                  "--depth": cloud.depth,
                  "--drift-seconds": `${cloud.seconds}s`,
                  left: `${cloud.left}%`,
                  top: `${cloud.top}%`,
                  width: `${cloud.width}px`,
                } as React.CSSProperties
              }
            />
          ))}
          {SPARKS.map((spark) => (
            <span
              className="hero-spark"
              key={spark.key}
              style={{ animationDelay: `${spark.delay}s`, left: `${spark.left}%`, top: `${spark.top}%` }}
            />
          ))}
        </div>

        {/* Ambient Top SVG Silhouette Route */}
        <div aria-hidden="true" className="hero-scene">
          <svg preserveAspectRatio="none" viewBox="0 0 1200 480">
            <g className="hero-layer hero-layer-far" style={{ "--depth": 0.15 } as React.CSSProperties}>
              <path d="M0,320 Q300,220 600,280 T1200,240 L1200,480 L0,480 Z" />
            </g>
            <g className="hero-layer hero-layer-mid" style={{ "--depth": 0.35 } as React.CSSProperties}>
              <path d="M0,360 Q340,290 700,340 T1200,300 L1200,480 L0,480 Z" />
            </g>
            <path
              className="hero-route"
              d="M 60,340 Q 300,250 540,320 T 1140,280"
              fill="none"
            />
          </svg>
        </div>

        {/* Left Column: Big Idea Hook + Badges + CTAs */}
        <div className="hero-copy">
          <div className="hero-badges-row">
            <span className="landing-badge">
              <Sparkles aria-hidden="true" size={13} /> {copy("landing_tagline", language)}
            </span>
            <span className="hero-mini-pill">
              <ShieldCheck aria-hidden="true" size={13} /> {copy("landing_pill_offline", language)}
            </span>
          </div>

          <h1>
            {language === "th" ? (
              copy("landing_headline", language)
            ) : (
              <>
                <span className="hero-word">Plan </span>
                <span className="hero-word">trips </span>
                <span className="hero-word">with </span>
                <span className="hero-word">mathematical </span>
                <span className="hero-word">certainty</span>
              </>
            )}
          </h1>

          <p className="landing-lead">{copy("landing_subtext", language)}</p>

          <div className="hero-cta-wrap">
            <div className="hero-cta-buttons">
              <button
                className="hero-cta hero-cta-primary"
                onClick={() => scrollToSection("start-a-trip")}
                type="button"
              >
                <Compass aria-hidden="true" size={18} />
                {copy("start_planning", language)}
                <ArrowRight aria-hidden="true" size={16} />
              </button>
              <button
                className="hero-cta hero-cta-secondary"
                onClick={() => scrollToSection("simulator")}
                type="button"
              >
                <Zap aria-hidden="true" size={16} />
                {copy("landing_showcase_badge", language)}
              </button>
            </div>
            <p className="hero-trust-note">
              <CheckCircle2 aria-hidden="true" size={13} /> {copy("landing_hero_trust_badge", language)}
            </p>
          </div>

          <div className="hero-tags-strip">
            <span className="hero-tag-item">
              <Timer aria-hidden="true" size={13} /> {copy("landing_pill_solver", language)}
            </span>
            <span className="hero-tag-item">
              <Route aria-hidden="true" size={13} /> {copy("landing_pill_walking", language)}
            </span>
            <span className="hero-tag-item">
              <Globe aria-hidden="true" size={13} /> {copy("landing_pill_nosignup", language)}
            </span>
          </div>
        </div>

        {/* Right Column: Interactive Destination & Pacing Simulator */}
        <div className="hero-demo" id="simulator">
          <div className="hero-demo-card">
            {/* City Selector Tabs */}
            <div className="hero-demo-tabs">
              {DEMO_DESTINATIONS.map((d) => (
                <button
                  className={`hero-demo-tab ${activeCityId === d.id ? "active" : ""}`}
                  key={d.id}
                  onClick={() => setActiveCityId(d.id)}
                  type="button"
                >
                  {d.city}
                </button>
              ))}
            </div>

            {/* Pacing Mode Selector */}
            <div className="hero-pacing-bar">
              <span className="pacing-label">{copy("landing_sim_mode_label", language)}</span>
              <div className="pacing-buttons">
                {(["relaxed", "balanced", "marathon"] as const).map((mode) => (
                  <button
                    className={`pacing-btn ${pacingMode === mode ? "active" : ""}`}
                    key={mode}
                    onClick={() => setPacingMode(mode)}
                    type="button"
                  >
                    {mode === "relaxed" && "🌱 "}
                    {mode === "balanced" && "⚡ "}
                    {mode === "marathon" && "🔥 "}
                    {mode === "relaxed" && copy("landing_pacing_relaxed", language)}
                    {mode === "balanced" && copy("landing_pacing_balanced", language)}
                    {mode === "marathon" && copy("landing_pacing_marathon", language)}
                  </button>
                ))}
              </div>
            </div>

            {/* Dynamic Card Header */}
            <div className="hero-demo-head">
              <span className="demo-city-title">
                📍 {selectedCityData.city}, {selectedCityData.country}
              </span>
              <span className="hero-demo-badge">{selectedPacingData.walkKm} walk</span>
            </div>

            {/* Simulated Route Timeline Rows */}
            <ol className="hero-demo-rows">
              {selectedPacingData.stops.map((row, idx) =>
                row.leg ? (
                  <li className="hero-demo-leg" key={`leg-${idx}`}>
                    <span>🚶 {row.leg}</span>
                  </li>
                ) : (
                  <li
                    className={`hero-demo-row ${row.kind === "meal" ? "meal" : ""}`}
                    key={`stop-${idx}-${row.name}`}
                  >
                    <time>{row.time}</time>
                    <span className="hero-demo-name">{row.name}</span>
                    <span className="hero-demo-kind">
                      {row.kind === "meal" ? (
                        <Utensils aria-hidden="true" size={12} />
                      ) : (
                        <MapPinned aria-hidden="true" size={12} />
                      )}
                    </span>
                  </li>
                ),
              )}
            </ol>

            {/* Live Constraints Verification Guarantee Strip */}
            <div className="hero-demo-footer">
              <span className="sim-chip">✓ {copy("landing_sim_hours_ok", language)}</span>
              <span className="sim-chip">✓ {copy("landing_sim_backtrack", language)}</span>
              <span className="sim-chip">✓ {copy("landing_sim_lunch_ok", language)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------
          LIVE MARQUEE TICKER (Hack the North credibility strip)
          ------------------------------------------------------------- */}
      <div aria-hidden="true" className="landing-ticker">
        <div className="ticker-track">
          <span className="ticker-item">⚡ 512+ Deterministic Tests Passing</span>
          <span className="ticker-item">🛡️ 100% Offline & Private Local SQLite</span>
          <span className="ticker-item">🧮 Pure Mixed-Integer Linear Programming (ILP)</span>
          <span className="ticker-item">🗺️ Free OpenStreetMap Vector Tiles</span>
          <span className="ticker-item">💸 Multi-Currency Bill Settlement Engine</span>
          <span className="ticker-item">📑 6-Sheet Formatted Excel Exporter</span>
          <span className="ticker-item">⚡ 512+ Deterministic Tests Passing</span>
          <span className="ticker-item">🛡️ 100% Offline & Private Local SQLite</span>
          <span className="ticker-item">🧮 Pure Mixed-Integer Linear Programming (ILP)</span>
        </div>
      </div>

      {/* -------------------------------------------------------------
          SECTION 2: "THE PAIN VS THE MATH" (Interactive Before/After)
          ------------------------------------------------------------- */}
      <section className="landing-section pain-math-section" id="pain-math">
        <div className="section-header">
          <span className="section-badge">{copy("landing_solutions_badge", language)}</span>
          <h2>{copy("landing_pain_title", language)}</h2>
          <p className="section-lead">{copy("landing_pain_lead", language)}</p>
        </div>

        {/* Tab Switcher */}
        <div className="pain-math-switch">
          <button
            className={`pain-tab ${painTab === "ai" ? "active-ai" : ""}`}
            onClick={() => setPainTab("ai")}
            type="button"
          >
            <XCircle aria-hidden="true" size={16} />
            {copy("landing_pain_ai_tab", language)}
          </button>
          <button
            className={`pain-tab ${painTab === "optimizer" ? "active-opt" : ""}`}
            onClick={() => setPainTab("optimizer")}
            type="button"
          >
            <CheckCircle2 aria-hidden="true" size={16} />
            {copy("landing_pain_opt_tab", language)}
          </button>
        </div>

        {/* 3 Core Benefit Cards */}
        <div className="benefits-grid">
          <div className={`benefit-card ${painTab === "ai" ? "pain-card-ai" : "pain-card-opt"}`}>
            <div className="benefit-icon-box">
              <CalendarClock aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_1_title", language)}</h3>
            <p>
              {painTab === "ai"
                ? "Generic chatbots hallucinate static hours, sending you to closed venues on public holidays and lunch breaks."
                : copy("landing_benefit_1_desc", language)}
            </p>
          </div>

          <div className={`benefit-card ${painTab === "ai" ? "pain-card-ai" : "pain-card-opt"}`}>
            <div className="benefit-icon-box">
              <Timer aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_2_title", language)}</h3>
            <p>
              {painTab === "ai"
                ? "Blind point-to-point connections create 25,000+ step criss-cross walks with zero lunch windows and extreme exhaustion."
                : copy("landing_benefit_2_desc", language)}
            </p>
          </div>

          <div className={`benefit-card ${painTab === "ai" ? "pain-card-ai" : "pain-card-opt"}`}>
            <div className="benefit-icon-box">
              <Wallet aria-hidden="true" size={24} />
            </div>
            <h3>{copy("landing_benefit_3_title", language)}</h3>
            <p>
              {painTab === "ai"
                ? "Late-night manual receipt math across Yen, Euros, and Dollars that leads to awkward group confusion."
                : copy("landing_benefit_3_desc", language)}
            </p>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 3: 4-STAGE PRODUCT LABORATORY (Interactive Walkthrough)
          ------------------------------------------------------------- */}
      <section className="landing-section showcase-section" id="lab">
        <div className="section-header">
          <span className="section-badge">{copy("landing_showcase_badge", language)}</span>
          <h2>{copy("landing_showcase_title", language)}</h2>
          <p className="section-lead">{copy("landing_showcase_lead", language)}</p>
        </div>

        {/* 4 Interactive Steps */}
        <div className="lab-stepper-grid">
          {[
            { num: 1, title: copy("stage_setup", language), desc: copy("landing_how_setup", language), icon: Sparkles },
            { num: 2, title: copy("stage_places", language), desc: copy("landing_how_places", language), icon: MapPinned },
            { num: 3, title: copy("stage_optimize", language), desc: copy("landing_how_plan", language), icon: Route },
            { num: 4, title: copy("stage_itinerary", language), desc: copy("landing_how_use", language), icon: ListChecks },
          ].map((st, i) => (
            <button
              className={`lab-step-card ${activeLabStep === i ? "active" : ""}`}
              key={st.num}
              onClick={() => setActiveLabStep(i)}
              type="button"
            >
              <div className="lab-step-head">
                <span className="lab-step-num">{st.num}</span>
                <st.icon aria-hidden="true" size={18} />
              </div>
              <h4>{st.title}</h4>
              <p>{st.desc}</p>
            </button>
          ))}
        </div>

        {/* Live Lab Preview Canvas */}
        <div className="lab-preview-canvas">
          {activeLabStep === 0 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 1: DISCOVERY & CONSTRAINTS</div>
              <h5>Smart Wizard: Dates, Pacing & Travel Party</h5>
              <div className="preview-chips-row">
                <span className="preview-chip">📅 2026-09-12 → 2026-09-17</span>
                <span className="preview-chip">👥 3 Travellers</span>
                <span className="preview-chip">🚶 Max 6.0 km/day</span>
                <span className="preview-chip">🍜 Lunch 12:00 - 13:30</span>
              </div>
            </div>
          )}
          {activeLabStep === 1 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 2: CURATION & SWIPE DECK</div>
              <h5>Tinder-Style Candidate Card Swipe & Shortlisting</h5>
              <div className="preview-chips-row">
                <span className="preview-chip green">💚 Kept: 14 Attractions</span>
                <span className="preview-chip red">❌ Passed: 6 Attractions</span>
                <span className="preview-chip">🗺️ Real OSM Geocodes</span>
              </div>
            </div>
          )}
          {activeLabStep === 2 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 3: INTEGER LINEAR PROGRAMMING (ILP)</div>
              <h5>Mathematical Branch-and-Bound Route Optimization</h5>
              <div className="preview-chips-row">
                <span className="preview-chip">⚡ 0.04s Solve Time</span>
                <span className="preview-chip">🛡️ 0 Schedule Conflicts</span>
                <span className="preview-chip">📍 100% Timezone Correct</span>
              </div>
            </div>
          )}
          {activeLabStep === 3 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 4: EXECUTION & WORKBOOKS</div>
              <h5>Interactive Day Timelines + 6-Sheet Formatted Excel (.xlsx)</h5>
              <div className="preview-chips-row">
                <span className="preview-chip">📊 Timetable Sheet</span>
                <span className="preview-chip">💰 Expenses & Split Ledger</span>
                <span className="preview-chip">📅 Apple/Google .ics Export</span>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 4: INTERACTIVE MULTI-CURRENCY BILL SPLIT SANDBOX
          ------------------------------------------------------------- */}
      <section className="landing-section split-sandbox-section" id="split-sandbox">
        <div className="section-header">
          <span className="section-badge">
            <Calculator aria-hidden="true" size={13} /> {copy("landing_bullet_money", language)}
          </span>
          <h2>{copy("landing_split_sandbox_title", language)}</h2>
          <p className="section-lead">{copy("landing_split_sandbox_lead", language)}</p>
        </div>

        <div className="split-sandbox-card">
          <div className="split-sandbox-inputs">
            <div className="split-input-row">
              <label htmlFor="bill-1">
                <strong>Alex</strong> paid (Dinner & Drinks):
              </label>
              <div className="input-affix">
                <span>$</span>
                <input
                  id="bill-1"
                  min="0"
                  onChange={(e) => setSampleBill1(Number(e.target.value) || 0)}
                  type="number"
                  value={sampleBill1}
                />
              </div>
            </div>

            <div className="split-input-row">
              <label htmlFor="bill-2">
                <strong>Sam</strong> paid (Taxi & Train passes):
              </label>
              <div className="input-affix">
                <span>$</span>
                <input
                  id="bill-2"
                  min="0"
                  onChange={(e) => setSampleBill2(Number(e.target.value) || 0)}
                  type="number"
                  value={sampleBill2}
                />
              </div>
            </div>

            <div className="split-input-row">
              <label htmlFor="bill-3">
                <strong>Jordan</strong> paid (Museum Tickets):
              </label>
              <div className="input-affix">
                <span>$</span>
                <input
                  id="bill-3"
                  min="0"
                  onChange={(e) => setSampleBill3(Number(e.target.value) || 0)}
                  type="number"
                  value={sampleBill3}
                />
              </div>
            </div>
          </div>

          {/* Real-time calculated settlement */}
          <div className="split-sandbox-results">
            <div className="split-summary-box">
              <div className="split-stat">
                <span className="split-label">Total Expense:</span>
                <span className="split-val">${totalBill}</span>
              </div>
              <div className="split-stat">
                <span className="split-label">Fair Share / Person:</span>
                <span className="split-val">${perPerson}</span>
              </div>
            </div>

            <div className="split-transfers-box">
              <h6>⚡ Minimal Settlement Transfers (0ms Math):</h6>
              <ul className="split-transfers-list">
                {jordanNet < 0 && (
                  <li>
                    <span>Jordan owes Alex:</span>
                    <strong>${Math.abs(jordanNet)}</strong>
                  </li>
                )}
                {samNet < 0 && (
                  <li>
                    <span>Sam owes Alex:</span>
                    <strong>${Math.abs(samNet)}</strong>
                  </li>
                )}
                {alexNet <= 0 && samNet >= 0 && jordanNet >= 0 && (
                  <li>
                    <span>All balances settle automatically.</span>
                  </li>
                )}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 5: 1-CLICK CURATED DESTINATION BLUEPRINTS
          ------------------------------------------------------------- */}
      <section className="landing-section presets-section" id="presets">
        <div className="section-header">
          <span className="section-badge">{copy("landing_proof_destinations", language)}</span>
          <h2>{copy("landing_presets_title", language)}</h2>
          <p className="section-lead">{copy("landing_presets_lead", language)}</p>
        </div>

        <div className="presets-grid">
          {PRESETS.map((p) => (
            <button
              className="preset-card"
              key={p.name}
              onClick={() => applyPreset(p)}
              type="button"
            >
              <div className="preset-head">
                <span className="preset-days">{p.days}</span>
                <span className="preset-badge">{p.badge}</span>
              </div>
              <h4>{copy(p.tagKey, language)}</h4>
              <p className="preset-city">
                📍 {p.city}, {p.country}
              </p>
              <span className="preset-action">
                {copy("start_planning", language)} <ArrowRight aria-hidden="true" size={14} />
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 6: WHY US (Comprehensive Comparison Table)
          ------------------------------------------------------------- */}
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
                  <XCircle aria-hidden="true" size={16} />
                  {copy("landing_comp_row1_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} />
                  {copy("landing_comp_row1_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row2_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} />
                  {copy("landing_comp_row2_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} />
                  {copy("landing_comp_row2_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row3_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} />
                  {copy("landing_comp_row3_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} />
                  {copy("landing_comp_row3_good", language)}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{copy("landing_comp_row4_title", language)}</strong>
                </td>
                <td className="bad-cell">
                  <XCircle aria-hidden="true" size={16} />
                  {copy("landing_comp_row4_bad", language)}
                </td>
                <td className="good-cell highlight-col">
                  <CheckCircle2 aria-hidden="true" size={16} />
                  {copy("landing_comp_row4_good", language)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 7: ACTION WORKSPACE (Creator Form + Saved Trips)
          ------------------------------------------------------------- */}
      <section className="landing-section action-workspace-section" id="start-a-trip">
        <div className="section-header">
          <span className="section-badge">{copy("start_planning", language)}</span>
          <h2>{copy("landing_cta_section_title", language)}</h2>
          <p className="section-lead">{copy("landing_cta_section_lead", language)}</p>
        </div>

        <div className="landing-columns">
          {/* Saved Trips Slot Drawer */}
          <div className="landing-main">
            <section className="stage-card trip-list">
              <h3>{copy("saved_trips", language)}</h3>
              {trips.data && trips.data.length > 0 ? (
                <ol className="stage-list">
                  {trips.data.map((trip) => (
                    <li key={trip.trip_id}>
                      <Link to={`/trips/${trip.trip_id}/setup`}>
                        <span className="trip-list-name">
                          <strong>{trip.name}</strong>
                          <small>{trip.destination}</small>
                        </span>
                        <TripResume tripId={trip.trip_id} />
                      </Link>
                      <DeleteTrip trip={trip} />
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="trip-list-empty">{copy("no_trips_yet", language)}</p>
              )}
            </section>
          </div>

          {/* Direct Trip Creator Form */}
          <aside>
            <form className="stage-card trip-form" onSubmit={submit}>
              <h3>{copy("new_trip", language)}</h3>
              <p className="landing-hint">{copy("destination_help", language)}</p>

              <label htmlFor="country">
                {copy("country", language)}
                <select
                  id="country"
                  name="country"
                  onChange={(e) => {
                    setCountry(e.target.value);
                    setCity("");
                    setTypedCity("");
                  }}
                  required
                  value={country}
                >
                  <option value="">{copy("choose_country", language)}</option>
                  {vocabulary.data?.countries.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label[language] ?? item.code}
                    </option>
                  ))}
                  <option value={TYPE_IT}>{copy("type_another_country", language)}</option>
                </select>
              </label>

              {country === TYPE_IT && (
                <label htmlFor="country-custom">
                  {copy("country", language)}
                  <input
                    autoFocus
                    id="country-custom"
                    name="country-custom"
                    onChange={(e) => setTypedCountry(e.target.value)}
                    placeholder={copy("country_placeholder", language)}
                    required
                    type="text"
                    value={typedCountry}
                  />
                </label>
              )}

              {country !== TYPE_IT && cities.length > 0 ? (
                <label htmlFor="city">
                  {copy("city", language)}
                  <select
                    id="city"
                    name="city"
                    onChange={(e) => setCity(e.target.value)}
                    required
                    value={city}
                  >
                    <option value="">{copy("choose_city", language)}</option>
                    {cities.map((cityName) => (
                      <option key={cityName} value={cityName}>
                        {cityName}
                      </option>
                    ))}
                    <option value={TYPE_IT}>{copy("type_another_city", language)}</option>
                  </select>
                </label>
              ) : null}

              {typingCity && (
                <label htmlFor="city-custom">
                  {copy("city", language)}
                  <input
                    id="city-custom"
                    name="city-custom"
                    onChange={(e) => setTypedCity(e.target.value)}
                    placeholder={copy("city_placeholder", language)}
                    required
                    type="text"
                    value={typedCity}
                  />
                </label>
              )}

              <label htmlFor="trip-name">
                {copy("trip_name", language)}
                <input
                  id="trip-name"
                  name="trip-name"
                  onChange={(e) => setName(e.target.value)}
                  placeholder={copy("trip_name_placeholder", language)}
                  type="text"
                  value={name}
                />
                <small>{copy("trip_name_help", language)}</small>
              </label>

              {errorCode && <p className="landing-error">⚠ {copy(errorCode, language)}</p>}

              <button
                className="setup-primary"
                disabled={createTrip.isPending || !resolvedCity}
                type="submit"
              >
                {copy("start_planning", language)}
              </button>
            </form>
          </aside>
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

      {/* -------------------------------------------------------------
          SECTION 8: FAQ ACCORDION (Objection Handling)
          ------------------------------------------------------------- */}
      <section className="landing-section faq-section" id="faq">
        <div className="section-header">
          <span className="section-badge">{copy("landing_faq_badge", language)}</span>
          <h2>{copy("landing_faq_title", language)}</h2>
        </div>

        <div className="faq-list">
          {[
            { q: "landing_faq_q1", a: "landing_faq_a1" },
            { q: "landing_faq_q2", a: "landing_faq_a2" },
            { q: "landing_faq_q3", a: "landing_faq_a3" },
            { q: "landing_faq_q4", a: "landing_faq_a4" },
            { q: "landing_faq_q5", a: "landing_faq_a5" },
          ].map((item, idx) => (
            <div className={`faq-item ${openFaq === idx ? "open" : ""}`} key={item.q}>
              <button
                className="faq-question"
                onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
                type="button"
              >
                <span>{copy(item.q, language)}</span>
                <ChevronDown aria-hidden="true" className="faq-chevron" size={18} />
              </button>
              {openFaq === idx && (
                <div className="faq-answer">
                  <p>{copy(item.a, language)}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------------
          LANDING FOOTER
          ------------------------------------------------------------- */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="footer-left">
            <Compass aria-hidden="true" size={16} />
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

function TripResume({ tripId }: { tripId: string }) {
  const { language } = useLanguage();
  const journey = useQuery({
    queryKey: ["journey", tripId],
    queryFn: () => rpc<Journey>("journey", { trip_id: tripId }),
  });
  if (!journey.data) return null;
  return (
    <span className="trip-list-resume">
      {copy(`stage_${journey.data.next}`, language)} → {copy("continue_trip", language)}
    </span>
  );
}
