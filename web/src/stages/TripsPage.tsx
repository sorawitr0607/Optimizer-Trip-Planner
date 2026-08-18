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
  Heart,
  ListChecks,
  MapPinned,
  Minus,
  Plus,
  Users,
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
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, rpc, type Journey, type SetupVocabulary, type Trip } from "../api/client";
import { copy, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { DeleteTrip } from "../shared/DeleteTrip";
import { useTheme } from "../shared/ThemeProvider";
import { startWorldMotion } from "../shared/worldMotion";

/** Sentinel for the typed fallback. Not a country code, so it cannot collide. */
const TYPE_IT = "__type_it__";

const BULLETS = [
  [MapPinned, "landing_bullet_places"],
  [CalendarClock, "landing_bullet_schedule"],
  [Wallet, "landing_bullet_money"],
  [FileSpreadsheet, "landing_bullet_export"],
] as const;

const TICKER_ITEMS = [
  [Zap, "landing_ticker_tests"],
  [ShieldCheck, "landing_ticker_local"],
  [Calculator, "landing_ticker_solver"],
  [Globe, "landing_ticker_maps"],
  [Wallet, "landing_ticker_split"],
  [FileSpreadsheet, "landing_ticker_export"],
] as const;

/**
 * The press, defined once for the whole page.
 *
 * SVG filter and pattern ids are document-global, so every scene on this page
 * references one set rather than carrying its own copy — which also means the
 * grain, the screens and the tear are literally the same effects everywhere,
 * and cannot drift apart between one band and the next.
 *
 * Rendered into a zero-size `<svg>`: it draws nothing itself and must not take
 * layout, but the definitions have to be in the document for the references to
 * resolve.
 */
function SceneDefs() {
  return (
    <svg aria-hidden="true" className="scene-defs" focusable="false">
      <defs>
        {/* Vector paths are exactly as straight as they are written, and nothing
            reads as digitally sterile faster than a hillside with a perfect edge.
            Displacing the outline by a few pixels of fractal noise gives the torn
            edge a scalpel and a sheet of paper actually make. Seeds are fixed, so
            the tear is identical on every render — a baseline photographs this. */}
        <filter height="112%" id="w-rough" width="112%" x="-6%" y="-6%">
          <feTurbulence baseFrequency="0.055 0.07" numOctaves="5" result="warp" seed="7" type="fractalNoise" />
          <feDisplacementMap in="SourceGraphic" in2="warp" scale="7" xChannelSelector="R" yChannelSelector="G" />
        </filter>

        {/* A gentler tear for small objects, which a landform's displacement
            would dissolve outright. */}
        <filter height="120%" id="w-rough-fine" width="120%" x="-10%" y="-10%">
          <feTurbulence baseFrequency="0.11" numOctaves="4" result="warp" seed="3" type="fractalNoise" />
          <feDisplacementMap in="SourceGraphic" in2="warp" scale="2.6" xChannelSelector="R" yChannelSelector="G" />
        </filter>

        <filter id="w-grain">
          <feTurbulence baseFrequency="0.72" numOctaves="4" seed="11" type="fractalNoise" />
          <feColorMatrix type="saturate" values="0" />
        </filter>

        <pattern height="6" id="w-halftone" patternUnits="userSpaceOnUse" width="6">
          <circle cx="1.5" cy="1.5" r="1.1" />
        </pattern>

        {/* One screen is a texture; two at different pitches and angles is a print. */}
        <pattern height="11" id="w-halftone-coarse" patternTransform="rotate(24)" patternUnits="userSpaceOnUse" width="11">
          <circle cx="2.6" cy="2.6" r="1.9" />
        </pattern>
      </defs>
    </svg>
  );
}

/**
 * A band of ground running along the foot of a section.
 *
 * The page below the world was a stack of coloured rectangles, and a rectangle is
 * where an illustrated journey stops being one. Each band carries the same two
 * hill layers, the same treeline, the same screens and the same torn edge as the
 * world above it, plus the dotted route continuing across — so scrolling reads as
 * walking on rather than as paging through.
 *
 * Scenery, so `aria-hidden`, no pointer events, and behind everything.
 */
function SceneBand({ flip = false }: { flip?: boolean }) {
  return (
    <div aria-hidden="true" className={`scene-band ${flip ? "flip" : ""}`}>
      <svg preserveAspectRatio="none" viewBox="0 0 1200 180">
        <g filter="url(#w-rough)">
          <path className="sb-far" d="M-40,86 Q150,52 360,80 T760,66 T1240,84 L1240,180 L-40,180 Z" />
          <path className="sb-screen" d="M-40,86 Q150,52 360,80 T760,66 T1240,84 L1240,180 L-40,180 Z" />
          <path className="sb-near" d="M-40,124 Q220,98 460,118 T900,106 T1240,122 L1240,180 L-40,180 Z" />
        </g>
        <g filter="url(#w-rough-fine)">
          <path
            className="sb-tree"
            d="M188,112 l-8,17 h3 l-6,14 h6 l-5,10 h16 l-5,-10 h6 l-6,-14 h3 Z M232,104 l-9,19 h3 l-7,15 h7 l-5,11 h18 l-5,-11 h7 l-7,-15 h3 Z M980,110 l-8,17 h3 l-6,14 h6 l-5,10 h16 l-5,-10 h6 l-6,-14 h3 Z M1028,116 l-8,15 h3 l-6,13 h6 l-5,9 h16 l-5,-9 h6 l-6,-13 h3 Z"
          />
          <path className="sb-bush" d="M520,152 a16,16 0 0 1 32,0 z M566,156 a11,11 0 0 1 22,0 z M700,154 a13,13 0 0 1 26,0 z" />
        </g>
        <path className="sb-path" d="M-20,158 Q260,132 520,146 T900,134 T1220,148" fill="none" />
        <rect className="w-grain" filter="url(#w-grain)" height="180" width="1200" x="0" y="0" />
      </svg>
    </div>
  );
}

/**
 * The world, and its landmarks.
 *
 * The brief for this section is that the page should feel like an illustrated
 * world rather than a site with pictures on it, and that the product's features
 * should be *places* in that world instead of a row of cards. So this is a scene
 * in five named layers, and each feature is an object standing somewhere in it.
 *
 * Every landmark is a real `<button>`. That matters more than it sounds: an
 * illustrated world that can only be used with a mouse is a worse page than the
 * cards it replaced, so each one carries its own accessible name from the
 * catalogue, takes focus in reading order, and opens on Enter or Space because
 * that is what a button already does. The scenery around them is `aria-hidden`,
 * because scenery is not information.
 *
 * The copy is the same bilingual catalogue the stage screens use — `stage_*` for
 * the name and `landing_how_*` for the description — so nothing here is a second
 * source of truth about what a stage does, and nothing is English-only.
 */
const LANDMARKS = [
  {
    id: "setup",
    nameKey: "stage_setup",
    descKey: "landing_how_setup",
    x: 13,
    y: 58,
    art: (
      /* Storybook proportions rather than architectural ones: the boards are
         nearly as wide as the object is tall and the post is a stub, because a
         signpost drawn to scale reads as a diagram and a signpost drawn top-heavy
         reads as a drawing of one. The same exaggeration runs through all four. */
      <>
        <path className="cut lm-post" d="M34 100 L34 52" />
        <path className="cut lm-sign" d="M-6 8 L54 2 L70 24 L54 46 L-6 40 Z" />
        <path className="cut lm-sign-alt" d="M60 54 L4 60 L-8 74 L4 88 L60 82 Z" />
      </>
    ),
  },
  {
    id: "places",
    nameKey: "stage_places",
    descKey: "landing_how_places",
    x: 33,
    y: 44,
    art: (
      <>
        <path className="cut lm-rock" d="M2 100 L14 74 L34 66 L54 74 L66 100 Z" />
        <circle className="cut lm-lens" cx="34" cy="34" r="32" />
        <circle className="cut lm-pupil" cx="34" cy="34" r="13" />
        <path className="cut lm-flag" d="M34 2 L34 -14 L72 -4 L34 6" />
      </>
    ),
  },
  {
    id: "optimize",
    nameKey: "stage_optimize",
    descKey: "landing_how_plan",
    x: 55,
    y: 56,
    art: (
      <>
        <path className="cut lm-plinth" d="M14 100 L20 82 L48 82 L54 100 Z" />
        <circle className="cut lm-dial" cx="34" cy="42" r="38" />
        <path className="cut lm-needle" d="M34 8 L48 42 L34 76 L20 42 Z" />
      </>
    ),
  },
  {
    id: "itinerary",
    nameKey: "stage_itinerary",
    descKey: "landing_how_use",
    x: 76,
    y: 46,
    art: (
      <>
        <path className="cut lm-post" d="M34 100 L34 56" />
        <path className="cut lm-board" d="M-4 2 L70 -4 L70 30 L-4 24 Z" />
        <path className="cut lm-board-alt" d="M2 36 L64 30 L64 62 L2 56 Z" />
      </>
    ),
  },
] as const;

/** One paper-cut object standing in the world, and the control that opens it. */
function Landmark({
  item,
  open,
  onOpen,
  language,
}: {
  item: (typeof LANDMARKS)[number];
  open: boolean;
  onOpen: () => void;
  language: Language;
}) {
  const name = copy(item.nameKey, language);
  /* The card is a sibling of the button, not a child of it. Nested, every word of
     the description became part of the button's own accessible name — screen
     readers announced "Trip and setup, Trip and setup, Answer a short form…" as
     the name of the control. A button is named by what it does; the card is the
     thing it discloses, so `aria-controls` and `aria-expanded` join them instead. */
  return (
    <div className={`landmark-place ${open ? "open" : ""}`} style={{ left: `${item.x}%`, top: `${item.y}%` }}>
      <button
        aria-controls={`landmark-card-${item.id}`}
        aria-expanded={open}
        className="landmark"
        onClick={onOpen}
        type="button"
      >
        <svg aria-hidden="true" className="landmark-art" focusable="false" viewBox="-14 -18 96 126">
          <defs>
            {/* The landmarks are cut paper too. They were the only objects in the
                world still carrying machine-exact edges, which is precisely the
                digitally-sterile look this art direction rules out. Finer than the
                landforms' tear, because these shapes are a tenth the size and a
                landform's displacement would dissolve them. */}
            <filter height="124%" id="lm-rough" width="124%" x="-12%" y="-12%">
              <feTurbulence baseFrequency="0.09" numOctaves="4" result="w" seed="5" type="fractalNoise" />
              <feDisplacementMap in="SourceGraphic" in2="w" scale="2.2" xChannelSelector="R" yChannelSelector="G" />
            </filter>
          </defs>
          <g filter="url(#lm-rough)">{item.art}</g>
        </svg>
        <span className="landmark-label">{name}</span>
      </button>
      <span className="landmark-card" id={`landmark-card-${item.id}`}>
        <span className="landmark-card-desc">{copy(item.descKey, language)}</span>
      </span>
    </div>
  );
}

/**
 * The drawn props.
 *
 * The reference layers painted objects across its scenes — a camera, a postcard,
 * framed photographs — and that layering is most of why its page reads as a place
 * rather than as boxes. Its artwork is commissioned and is not ours to take, so
 * this is the same *idea* in the vocabulary the hero already speaks: flat SVG,
 * one stroke weight, coloured entirely from tokens.
 *
 * Everything here is decoration and behaves like it. Nothing carries meaning that
 * is not also written somewhere, every prop is `aria-hidden`, none of it takes a
 * pointer event, and the whole layer is absent from the accessibility tree. The
 * shapes are travel objects rather than generic ornament because the page is
 * about trips: a postcard, a stamp, a compass, a ticket, a pin, a paper plane.
 */
const PROPS = {
  postcard: (
    <>
      <rect height="86" rx="2" width="124" x="4" y="10" />
      <path d="M4 34 h124" />
      <path d="M96 14 h28 v20 h-28 z" />
      <path d="M14 48 h60 M14 60 h48 M14 72 h66" />
    </>
  ),
  compass: (
    <>
      <circle cx="52" cy="52" r="44" />
      <circle cx="52" cy="52" r="34" />
      <path d="M52 22 L62 52 L52 82 L42 52 Z" />
      <path d="M22 52 h12 M70 52 h12 M52 14 v10 M52 80 v10" />
    </>
  ),
  ticket: (
    <>
      <path d="M4 22 h60 a10 10 0 0 0 20 0 h44 v56 h-44 a10 10 0 0 0 -20 0 h-60 z" />
      <path d="M74 30 v6 M74 46 v6 M74 62 v6" />
      <path d="M14 40 h40 M14 54 h28" />
    </>
  ),
  plane: (
    <>
      <path d="M6 46 L106 12 L74 92 L58 60 Z" />
      <path d="M58 60 L106 12" />
    </>
  ),
  pin: (
    <>
      <path d="M40 8 a28 28 0 0 1 28 28 c0 20 -28 48 -28 48 S12 56 12 36 A28 28 0 0 1 40 8 Z" />
      <circle cx="40" cy="36" r="10" />
    </>
  ),
  suitcase: (
    <>
      <rect height="60" rx="3" width="96" x="18" y="34" />
      <path d="M46 34 v-12 a6 6 0 0 1 6 -6 h28 a6 6 0 0 1 6 6 v12" />
      <path d="M18 56 h96" />
    </>
  ),
  boardingPass: (
    <>
      <path d="M6 26 h118 v52 h-118 z" />
      <path d="M90 26 v52" strokeDasharray="5 4" />
      <path d="M16 42 h56 M16 56 h38" />
      <circle cx="107" cy="46" r="7" />
    </>
  ),
  foldedMap: (
    <>
      <path d="M8 26 L48 14 L88 30 L126 16 L126 82 L88 96 L48 80 L8 92 Z" />
      <path d="M48 14 v66 M88 30 v66" strokeDasharray="5 4" />
      <path d="M24 52 q18 -12 36 2 t34 -6" />
    </>
  ),
  luggageTag: (
    <>
      <path d="M34 12 h64 a8 8 0 0 1 8 8 v52 a8 8 0 0 1 -8 8 h-64 l-22 -34 z" />
      <circle cx="30" cy="46" r="7" />
      <path d="M52 36 h40 M52 52 h28" />
    </>
  ),
  stamp: (
    <>
      <path d="M8 8 h80 v80 h-80 z" strokeDasharray="6 5" />
      <path d="M22 62 L38 40 L50 54 L62 34 L74 62 Z" />
      <circle cx="34" cy="26" r="6" />
    </>
  ),
} as const;

/** One decorative prop, positioned by its section's own stylesheet rule. */
function SceneProp({ kind, place }: { kind: keyof typeof PROPS; place: string }) {
  return (
    <svg
      aria-hidden="true"
      className={`scene-prop scene-prop-${place}`}
      filter="url(#w-rough-fine)"
      fill="none"
      focusable="false"
      viewBox="0 0 132 104"
    >
      {PROPS[kind]}
    </svg>
  );
}

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
    badge: "Wine & Bridges",
    currency: "EUR (€)",
    pacing: {
      relaxed: {
        walkKm: "2.8 km",
        stopsCount: 4,
        stops: [
          { time: "09:30", name: "São Bento Tile Station", kind: "visit" },
          { leg: "6 min walk (400m)", time: "", name: "", kind: "visit" },
          { time: "11:00", name: "Livraria Lello Historic Bookstore", kind: "visit" },
          { leg: "8 min walk (500m)", time: "", name: "", kind: "visit" },
          { time: "12:30", name: "Ribeira Riverfront Seafood Lunch", kind: "meal" },
          { leg: "12 min river stroll", time: "", name: "", kind: "visit" },
          { time: "15:00", name: "Vila Nova de Gaia Port Cellars", kind: "visit" },
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
        walkKm: "7.8 km",
        stopsCount: 8,
        stops: [
          { time: "08:30", name: "Clérigos Tower Panorama Climb", kind: "visit" },
          { leg: "10 min walk (700m)", time: "", name: "", kind: "visit" },
          { time: "09:45", name: "São Bento & Cathedral Cloisters", kind: "visit" },
          { leg: "8 min walk (550m)", time: "", name: "", kind: "visit" },
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
          { time: "17:30", name: "Ginza Kaiseki Dinner", kind: "meal" },
        ],
      },
      balanced: {
        walkKm: "5.8 km",
        stopsCount: 6,
        stops: [
          { time: "09:00", name: "Senso-ji Asakusa Pagoda", kind: "visit" },
          { leg: "8 min walk (500m)", time: "", name: "", kind: "visit" },
          { time: "10:30", name: "Sumida River Promenade", kind: "visit" },
          { leg: "14 min transit", time: "", name: "", kind: "visit" },
          { time: "12:15", name: "Tsukiji Outer Market Fresh Sushi", kind: "meal" },
          { leg: "12 min transit", time: "", name: "", kind: "visit" },
          { time: "14:00", name: "Meiji Jingu Shrine & Forest", kind: "visit" },
          { leg: "10 min walk (700m)", time: "", name: "", kind: "visit" },
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
    badge: "Waterfalls & Geysers",
    currency: "ISK (kr)",
    pacing: {
      relaxed: {
        walkKm: "2.4 km",
        stopsCount: 3,
        stops: [
          { time: "10:00", name: "Hallgrímskirkja Bell Tower View", kind: "visit" },
          { leg: "10 min town walk (600m)", time: "", name: "", kind: "visit" },
          { time: "12:00", name: "Harpa Concert Hall & Warm Rye Lunch", kind: "meal" },
          { leg: "25 min scenic drive", time: "", name: "", kind: "visit" },
          { time: "14:30", name: "Sky Lagoon Geothermal Soak", kind: "visit" },
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
] as const;

const SWIPE_CANDIDATES = [
  {
    city: "Tokyo",
    country: "Japan",
    name: "Senso-ji Ancient Temple & Five-Story Pagoda",
    tag: "Cultural Heritage",
    meta: "⭐ 4.8 · Open 06:00 - 17:00 · Free Entry",
  },
  {
    city: "Taipei",
    country: "Taiwan",
    name: "Longshan Historic Temple & Herb Lane",
    tag: "Incense Alleys & Food",
    meta: "⭐ 4.7 · Open 06:00 - 22:00 · Free Entry",
  },
  {
    city: "Porto",
    country: "Portugal",
    name: "São Bento Azulejo Tile Station",
    tag: "Architectural Marvel",
    meta: "⭐ 4.9 · Open 24 Hours · Free Entry",
  },
  {
    city: "Reykjavík",
    country: "Iceland",
    name: "Hallgrímskirkja Bell Tower View",
    tag: "Panoramic Landmark",
    meta: "⭐ 4.8 · Open 09:00 - 17:00 · Elevator Pass ISK 1,400",
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

  // Interactive Simulator State
  const [activeCityId, setActiveCityId] = useState<"porto" | "taipei" | "tokyo" | "reykjavik">("porto");
  const [pacingMode, setPacingMode] = useState<PacingMode>("balanced");

  // Interactive Pain/Math Tabs
  const [painTab, setPainTab] = useState<"ai" | "optimizer">("optimizer");

  // Interactive Product Lab Stepper
  const [activeLabStep, setActiveLabStep] = useState<number>(0);
  const [labPartySize, setLabPartySize] = useState<number>(3);
  const [labPacing, setLabPacing] = useState<PacingMode>("balanced");
  const [labKeptCount, setLabKeptCount] = useState<number>(14);
  const [labPassedCount, setLabPassedCount] = useState<number>(6);
  const [labSwipeIdx, setLabSwipeIdx] = useState<number>(0);
  const [labSolving, setLabSolving] = useState<boolean>(false);
  const [labExcelTab, setLabExcelTab] = useState<number>(0);

  // Interactive Split Calculator Sandbox State
  const [splitCurrency, setSplitCurrency] = useState<string>("$");
  const [sampleBill1, setSampleBill1] = useState<number>(120);
  const [sampleBill2, setSampleBill2] = useState<number>(60);
  const [sampleBill3, setSampleBill3] = useState<number>(45);

  // FAQ Accordion State
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  /** Which landmark has its card unfolded. One at a time, like a map legend. */
  const [openLandmark, setOpenLandmark] = useState<string | null>(null);
  const worldRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!worldRef.current) return;
    return startWorldMotion(worldRef.current);
  }, []);

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
    <main
      className="landing"
      ref={worldRef}
      onPointerMove={(e) => {
        // One handler for the page. The hero writes these on itself as well, which
        // simply wins inside the hero; every other scene's props read them here.
        const rect = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty("--drift-x", String((e.clientX - rect.left) / rect.width - 0.5));
        e.currentTarget.style.setProperty("--drift-y", String((e.clientY - rect.top) / rect.height - 0.5));
      }}
    >
      <SceneDefs />
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
          <button onClick={() => scrollToSection("pain-math")} type="button">
            {copy("landing_nav_story", language)}
          </button>
          <button onClick={() => scrollToSection("lab")} type="button">
            {copy("landing_nav_demo", language)}
          </button>
          <button onClick={() => scrollToSection("split-sandbox")} type="button">
            {copy("landing_nav_split", language)}
          </button>
          <button onClick={() => scrollToSection("comparison")} type="button">
            {copy("landing_nav_compare", language)}
          </button>
          <button onClick={() => scrollToSection("faq")} type="button">
            {copy("landing_nav_faq", language)}
          </button>
        </div>
        <div className="landing-controls">
          <button
            className="landing-nav-start"
            onClick={() => scrollToSection("start-a-trip")}
            type="button"
          >
            {copy("landing_nav_start", language)}
          </button>
          <button
            aria-label={copy("switch_language", language)}
            className="landing-icon-control"
            onClick={() => setLanguage(language === "en" ? "th" : "en")}
            type="button"
          >
            <Languages aria-hidden="true" size={16} />
            <span className="control-label">{language === "en" ? "ไทย" : "English"}</span>
          </button>
          <button
            aria-label={copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
            className="landing-icon-control"
            onClick={toggleTheme}
            type="button"
          >
            <SunMoon aria-hidden="true" size={16} />
            <span className="control-label">
              {copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
            </span>
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
        <img alt="" aria-hidden="true" className="scene-art scene-art-hero" loading="lazy" src="/illustrations/travel-mode.svg" />
        <div aria-hidden="true" className="hero-scene">
          <svg preserveAspectRatio="none" viewBox="0 0 1200 480">
            {/* Two ranges, far hazier than near, which is the whole trick to depth
                in a flat drawing — and the reason they carry different `--depth`
                values, so the pointer parallax separates them as well. */}
            <g className="hero-layer hero-range-far" filter="url(#w-rough)" style={{ "--depth": 0.12 } as React.CSSProperties}>
              <path d="M0,306 L88,252 L146,284 L238,208 L326,278 L408,238 L498,292 L598,242 L688,288 L778,226 L878,284 L978,246 L1078,290 L1158,256 L1200,286 L1200,480 L0,480 Z" />
              <path
                className="hero-snow"
                d="M238,208 L262,229 L250,232 L238,226 L226,233 L214,229 Z M778,226 L802,247 L790,250 L778,244 L766,251 L754,247 Z"
              />
            </g>
            <g className="hero-layer hero-range-mid" filter="url(#w-rough)" style={{ "--depth": 0.26 } as React.CSSProperties}>
              <path d="M0,356 L118,302 L208,338 L300,264 L398,332 L518,290 L618,346 L718,298 L838,342 L938,302 L1058,348 L1158,314 L1200,338 L1200,480 L0,480 Z" />
              <path
                className="hero-snow"
                d="M300,264 L326,287 L313,290 L300,283 L287,291 L274,287 Z M718,298 L744,321 L731,324 L718,317 L705,325 L692,321 Z"
              />
            </g>
            {/* The warm foreground the ranges stand on. */}
            {/* The planted middle band. Without it the scene is two silhouettes
                and a beach; the reference's own hero has a green shoulder under
                its peaks, a treeline on it, and foliage scattered in front. */}
            <g className="hero-layer hero-hills" filter="url(#w-rough)" style={{ "--depth": 0.34 } as React.CSSProperties}>
              <path d="M0,392 Q140,362 300,388 T620,380 T900,392 T1200,384 L1200,480 L0,480 Z" />
              <path
                className="hero-hill-deep"
                d="M556,400 Q700,366 862,392 T1200,380 L1200,480 L556,480 Z"
              />
              {/* Trees keep to the right of the copy column: this green measures
                  2.69 against body text, so it must never sit behind a word. */}
              <path className="hero-tree" d="M628,364 l-8,17 h3 l-6,14 h6 l-5,10 h16 l-5,-10 h6 l-6,-14 h3 Z M666,354 l-7,21 h3 l-6,17 h5 l-4,12 h14 l-4,-12 h5 l-6,-17 h3 Z M694,357 l-7,20 h3 l-6,16 h5 l-4,11 h14 l-4,-11 h5 l-6,-16 h3 Z M731,356 l-7,20 h3 l-6,16 h5 l-4,12 h14 l-4,-12 h5 l-6,-16 h3 Z M773,368 l-7,15 h3 l-6,12 h5 l-4,9 h14 l-4,-9 h5 l-6,-12 h3 Z M801,361 l-10,18 h4 l-8,15 h7 l-6,10 h20 l-6,-10 h7 l-8,-15 h4 Z M829,367 l-7,16 h3 l-6,13 h5 l-4,9 h14 l-4,-9 h5 l-6,-13 h3 Z M872,361 l-7,18 h3 l-6,15 h5 l-4,10 h14 l-4,-10 h5 l-6,-15 h3 Z M916,371 l-8,14 h3 l-6,11 h6 l-5,8 h16 l-5,-8 h6 l-6,-11 h3 Z M960,373 l-11,13 h4 l-9,11 h8 l-7,7 h22 l-7,-7 h8 l-9,-11 h4 Z M1004,362 l-7,18 h3 l-6,14 h5 l-4,10 h14 l-4,-10 h5 l-6,-14 h3 Z M1037,373 l-11,13 h4 l-9,11 h8 l-7,7 h22 l-7,-7 h8 l-9,-11 h4 Z M1067,365 l-10,16 h4 l-8,13 h7 l-6,9 h20 l-6,-9 h7 l-8,-13 h4 Z M1097,357 l-7,20 h3 l-6,16 h5 l-4,11 h14 l-4,-11 h5 l-6,-16 h3 Z M1141,365 l-11,16 h4 l-9,13 h8 l-7,9 h22 l-7,-9 h8 l-9,-13 h4 Z M1172,371 l-11,14 h4 l-9,11 h8 l-7,8 h22 l-7,-8 h8 l-9,-11 h4 Z" />
            </g>

            {/* The warm foreground the whole scene stands on. */}
            <g className="hero-layer hero-range-near" filter="url(#w-rough)" style={{ "--depth": 0.5 } as React.CSSProperties}>
              <path d="M0,428 Q180,404 380,424 T760,418 T1200,426 L1200,480 L0,480 Z" />
              <path className="hero-bush" d="M79,460 a17,17 0 0 1 34,0 z M120,462 a12,12 0 0 1 24,0 z M53,464 a11,11 0 0 1 22,0 z M255,468 a13,13 0 0 1 26,0 z M284,466 a16,16 0 0 1 32,0 z M990,465 a14,14 0 0 1 28,0 z M1031,468 a11,11 0 0 1 22,0 z" />
              <path className="hero-rock" d="M419,474 q5,-13,13,-12 q9,-3,13,12 z M865,470 q6,-15,15,-14 q10,-3,15,14 z M690,478 q4,-10,10,-9 q7,-2,10,9 z" />
              <path className="hero-bloom" d="M180,466 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M214,458 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M352,464 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M388,470 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M946,466 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M1084,460 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M520,470 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0" />
            </g>

            <path
              className="hero-route"
              d="M 60,340 Q 300,250 540,320 T 1140,280"
              fill="none"
            />
            {/* The same press as the world below: two screens at different
                pitches, then the grain over everything, last. */}
            <path className="w-screen" d="M0,356 L118,302 L208,338 L300,264 L398,332 L518,290 L618,346 L718,298 L838,342 L938,302 L1058,348 L1158,314 L1200,338 L1200,480 L0,480 Z" />
            <path className="w-screen-coarse" d="M0,428 Q180,404 380,424 T760,418 T1200,426 L1200,480 L0,480 Z" />
            <rect className="w-grain" filter="url(#w-grain)" height="480" width="1200" x="0" y="0" />
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
                <span className="hero-word">around </span>
                <span className="hero-word">real-world </span>
                <span className="hero-word">constraints</span>
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
                  aria-pressed={activeCityId === d.id}
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
                    aria-pressed={pacingMode === mode}
                    className={`pacing-btn ${pacingMode === mode ? "active" : ""}`}
                    key={mode}
                    onClick={() => setPacingMode(mode)}
                    type="button"
                  >
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
                <MapPinned aria-hidden="true" size={13} /> {selectedCityData.city}, {selectedCityData.country}
              </span>
              <span className="hero-demo-badge">{selectedPacingData.walkKm} walk</span>
            </div>

            {/* Simulated Route Timeline Rows */}
            <ol className="hero-demo-rows">
              {selectedPacingData.stops.map((row, idx) =>
                row.leg ? (
                  <li className="hero-demo-leg" key={`leg-${idx}`}>
                    <span><Route aria-hidden="true" size={13} /> {row.leg}</span>
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
              <span className="sim-chip"><CheckCircle2 aria-hidden="true" size={13} /> {copy("landing_sim_hours_ok", language)}</span>
              <span className="sim-chip"><CheckCircle2 aria-hidden="true" size={13} /> {copy("landing_sim_backtrack", language)}</span>
              <span className="sim-chip"><CheckCircle2 aria-hidden="true" size={13} /> {copy("landing_sim_lunch_ok", language)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------
          THE ILLUSTRATED WORLD

          Five named layers, back to front, and the product's four stages
          standing in it as places rather than sitting beside it as cards. The
          terrain is continuous with the hero above and the band below, which is
          the point: no scene on this page ends in a straight horizontal line.
          ------------------------------------------------------------- */}
      <section aria-labelledby="world-title" className="landing-world" id="world">
        <div className="world-copy">
          <span className="section-badge">{copy("landing_showcase_badge", language)}</span>
          <h2 id="world-title">{copy("landing_showcase_title", language)}</h2>
          <p className="section-lead">{copy("landing_showcase_lead", language)}</p>
        </div>

        {/* Layers 1-3 and 5 are scenery and say so; only the landmarks are content. */}
        <div aria-hidden="true" className="world-scenery">
          <svg className="world-svg" preserveAspectRatio="xMidYMax slice" viewBox="0 0 1200 620">
            {/* LAYER 2 — distant scenery */}
            <g className="w-layer w-distant" filter="url(#w-rough)" style={{ "--depth": 0.1 } as React.CSSProperties}>
              <path className="w-peak-far" d="M-40,300 L120,176 L210,244 L330,140 L452,250 L560,186 L680,262 L800,168 L930,252 L1040,190 L1160,258 L1240,214 L1240,620 L-40,620 Z" />
              <path className="w-snow" d="M330,140 L364,172 L346,177 L330,168 L314,180 L296,172 Z M800,168 L834,200 L816,205 L800,196 L784,208 L766,200 Z" />
              <path className="w-peak-mid" d="M-40,352 L100,262 L220,338 L360,240 L500,330 L640,268 L790,344 L920,262 L1060,340 L1180,286 L1240,330 L1240,620 L-40,620 Z" />
              <path className="w-screen" d="M-40,352 L100,262 L220,338 L360,240 L500,330 L640,268 L790,344 L920,262 L1060,340 L1180,286 L1240,330 L1240,620 L-40,620 Z" />
            </g>

            {/* LAYER 3 — middle scenery */}
            <g className="w-layer w-middle" filter="url(#w-rough)" style={{ "--depth": 0.26 } as React.CSSProperties}>
              <path className="w-hill" d="M-40,430 Q140,384 340,418 T720,404 T1060,428 T1240,410 L1240,620 L-40,620 Z" />
              <path className="w-hill-deep" d="M620,452 Q800,410 980,442 T1240,428 L1240,620 L620,620 Z" />
              <path className="w-tree" d="M690,442 l-9,20 h4 l-7,16 h7 l-6,12 h22 l-6,-12 h7 l-7,-16 h4 Z M742,432 l-10,22 h4 l-8,18 h8 l-6,13 h24 l-6,-13 h8 l-8,-18 h4 Z M800,440 l-9,20 h4 l-7,17 h7 l-6,12 h22 l-6,-12 h7 l-7,-17 h4 Z M1054,436 l-10,21 h4 l-8,17 h8 l-6,13 h24 l-6,-13 h8 l-8,-17 h4 Z M1108,446 l-9,19 h4 l-7,16 h7 l-6,11 h22 l-6,-11 h7 l-7,-16 h4 Z" />
            </g>

            {/* LAYER 4 — the ground the landmarks stand on */}
            <g className="w-layer w-ground" filter="url(#w-rough)" style={{ "--depth": 0.46 } as React.CSSProperties}>
              <path className="w-terrain" d="M-40,506 Q160,470 380,498 T760,486 T1240,504 L1240,620 L-40,620 Z" />
              <path className="w-screen-warm" d="M-40,506 Q160,470 380,498 T760,486 T1240,504 L1240,620 L-40,620 Z" />
              <path className="w-screen-coarse" d="M-40,506 Q160,470 380,498 T760,486 T1240,504 L1240,620 L-40,620 Z" />
              {/* Rough shading: the ground darkens where it meets the hill behind
                  it, painted as its own translucent shape rather than a gradient,
                  because a gradient is the smooth thing this is avoiding. */}
              <path className="w-shade" d="M-40,506 Q160,470 380,498 T760,486 T1240,504 L1240,548 Q760,528 380,540 T-40,548 Z" />
              <path className="w-path" d="M-20,592 Q220,548 430,566 T820,540 T1220,556" fill="none" />
            </g>

            {/* LAYER 5 — decorative foreground */}
            <g className="w-layer w-front" filter="url(#w-rough-fine)" style={{ "--depth": 0.72 } as React.CSSProperties}>
              <path className="w-bush" d="M92,590 a20,20 0 0 1 40,0 z M138,596 a13,13 0 0 1 26,0 z M362,596 a17,17 0 0 1 34,0 z M902,592 a15,15 0 0 1 30,0 z M1128,598 a12,12 0 0 1 24,0 z" />
              <path className="w-bloom" d="M214,600 m-5,0 a5,5 0 1 0 10,0 a5,5 0 1 0 -10,0 M262,592 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0 M486,602 m-5,0 a5,5 0 1 0 10,0 a5,5 0 1 0 -10,0 M978,598 m-4,0 a4,4 0 1 0 8,0 a4,4 0 1 0 -8,0" />
              <path className="w-rock" d="M556,604 q7,-16,16,-15 q11,-3,16,15 z M1046,600 q6,-14,14,-13 q10,-3,14,13 z" />
            </g>

            {/* The grain, over everything, last. */}
            <rect className="w-grain" filter="url(#w-grain)" height="620" width="1200" x="0" y="0" />
          </svg>
        </div>

        {/* Four features, standing in the world as places. */}
        <div className="world-landmarks">
          {LANDMARKS.map((item) => (
            <Landmark
              item={item}
              key={item.id}
              language={language}
              onOpen={() => setOpenLandmark(openLandmark === item.id ? null : item.id)}
              open={openLandmark === item.id}
            />
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------------
          LIVE MARQUEE TICKER (Hack the North credibility strip)
          ------------------------------------------------------------- */}
      <div aria-hidden="true" className="landing-ticker">
        <div className="ticker-track">
          {[...TICKER_ITEMS, ...TICKER_ITEMS].map(([Icon, code], index) => (
            <span className="ticker-item" key={`${code}-${index}`}>
              <Icon aria-hidden="true" size={13} /> {copy(code, language)}
            </span>
          ))}
        </div>
      </div>

      {/* -------------------------------------------------------------
          SECTION 2: "THE PAIN VS THE MATH" (Interactive Before/After)
          ------------------------------------------------------------- */}
      <section className="landing-section pain-math-section" id="pain-math">
        <SceneBand />
        <SceneProp kind="foldedMap" place="mid" />
        <SceneProp kind="compass" place="tl" />
        <SceneProp kind="stamp" place="br" />
        <div className="section-header">
          <span className="section-badge">{copy("landing_solutions_badge", language)}</span>
          <h2>{copy("landing_pain_title", language)}</h2>
          <p className="section-lead">{copy("landing_pain_lead", language)}</p>
        </div>

        {/* Tab Switcher */}
        <div className="pain-math-switch">
          <button
            aria-pressed={painTab === "ai"}
            className={`pain-tab ${painTab === "ai" ? "active-ai" : ""}`}
            onClick={() => setPainTab("ai")}
            type="button"
          >
            <XCircle aria-hidden="true" size={16} />
            {copy("landing_pain_ai_tab", language)}
          </button>
          <button
            aria-pressed={painTab === "optimizer"}
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
                ? copy("landing_benefit_1_risk", language)
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
                ? copy("landing_benefit_2_risk", language)
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
                ? copy("landing_benefit_3_risk", language)
                : copy("landing_benefit_3_desc", language)}
            </p>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 3: 4-STAGE PRODUCT LABORATORY (Interactive Walkthrough)
          ------------------------------------------------------------- */}
      <section className="landing-section showcase-section" id="lab">
        <SceneBand flip />
        <SceneProp kind="suitcase" place="bl" />
        <img
          alt=""
          aria-hidden="true"
          className="scene-art"
          loading="lazy"
          src="/illustrations/adventure-map.svg"
        />
        <SceneProp kind="ticket" place="tr" />
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
              aria-controls="lab-preview-panel"
              aria-pressed={activeLabStep === i}
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
        <div aria-live="polite" className="lab-preview-canvas" id="lab-preview-panel">
          {activeLabStep === 0 && (
            <div className="lab-preview-content">
              <div className="preview-tag">{copy("landing_lab_stage1", language)}</div>
              <h5>{copy("landing_lab_stage1_title", language)}</h5>
              <div className="lab-interactive-row">
                <div className="lab-control-group">
                  <span className="lab-control-label">{copy("landing_lab_party", language)}</span>
                  <div className="lab-counter">
                    <button
                      aria-label={copy("landing_lab_decrease", language)}
                      className="lab-counter-btn"
                      disabled={labPartySize <= 1}
                      onClick={() => setLabPartySize((p) => Math.max(1, p - 1))}
                      type="button"
                    >
                      <Minus aria-hidden="true" size={13} />
                    </button>
                    <span className="lab-counter-val">{labPartySize} {copy("travellers", language)}</span>
                    <button
                      aria-label={copy("landing_lab_increase", language)}
                      className="lab-counter-btn"
                      disabled={labPartySize >= 12}
                      onClick={() => setLabPartySize((p) => Math.min(12, p + 1))}
                      type="button"
                    >
                      <Plus aria-hidden="true" size={13} />
                    </button>
                  </div>
                </div>

                <div className="lab-control-group">
                  <span className="lab-control-label">{copy("landing_sim_mode_label", language)}</span>
                  <div className="lab-pills">
                    {(["relaxed", "balanced", "marathon"] as const).map((p) => (
                      <button
                        aria-pressed={labPacing === p}
                        className={`lab-pill-btn ${labPacing === p ? "active" : ""}`}
                        key={p}
                        onClick={() => setLabPacing(p)}
                        type="button"
                      >
                        {p === "relaxed" && `🌱 ${copy("landing_pacing_relaxed", language)}`}
                        {p === "balanced" && `⚡ ${copy("landing_pacing_balanced", language)}`}
                        {p === "marathon" && `🔥 ${copy("landing_pacing_marathon", language)}`}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="preview-chips-row">
                <span className="preview-chip"><CalendarClock aria-hidden="true" size={13} /> 2026-09-12 → 2026-09-17 (6 {copy("days", language)})</span>
                <span className="preview-chip"><Users aria-hidden="true" size={13} /> {labPartySize} {copy("travellers", language)}</span>
                <span className="preview-chip">
                  <Route aria-hidden="true" size={13} /> {copy("landing_lab_walk_cap", language)}: {labPacing === "relaxed" ? "3.5" : labPacing === "balanced" ? "5.8" : "8.5"} km ({labPacing === "relaxed" ? "~4,500" : labPacing === "balanced" ? "~8,200" : "~13,500"} steps)
                </span>
                <span className="preview-chip"><Wallet aria-hidden="true" size={13} /> Est. Budget: {labPacing === "relaxed" ? "$55/day" : labPacing === "balanced" ? "$110/day" : "$195/day"}</span>
                <span className="preview-chip"><Utensils aria-hidden="true" size={13} /> {copy("landing_lab_lunch", language)} 12:00 - 13:30</span>
              </div>
            </div>
          )}

          {activeLabStep === 1 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 2: CURATION & SWIPE DECK</div>
              <h5>Candidate Specimen Card Swipe & Shortlisting</h5>
              
              <div className="lab-swipe-card-preview">
                <div className="swipe-card-info">
                  <div className="swipe-card-badge">📍 {SWIPE_CANDIDATES[labSwipeIdx].city}, {SWIPE_CANDIDATES[labSwipeIdx].country} · {SWIPE_CANDIDATES[labSwipeIdx].tag}</div>
                  <h6>{SWIPE_CANDIDATES[labSwipeIdx].name}</h6>
                  <p>{SWIPE_CANDIDATES[labSwipeIdx].meta}</p>
                </div>
                <div className="swipe-card-actions">
                  <button
                    className="swipe-btn pass"
                    onClick={() => {
                      setLabPassedCount((c) => c + 1);
                      setLabSwipeIdx((i) => (i + 1) % SWIPE_CANDIDATES.length);
                    }}
                    type="button"
                  >
                    <XCircle aria-hidden="true" size={16} /> Pass
                  </button>
                  <button
                    className="swipe-btn keep"
                    onClick={() => {
                      setLabKeptCount((c) => c + 1);
                      setLabSwipeIdx((i) => (i + 1) % SWIPE_CANDIDATES.length);
                    }}
                    type="button"
                  >
                    <Heart aria-hidden="true" size={16} /> Want to Visit
                  </button>
                </div>
              </div>

              <div className="preview-chips-row">
                <span className="preview-chip green"><CheckCircle2 aria-hidden="true" size={13} /> Kept: {labKeptCount} Attractions</span>
                <span className="preview-chip red"><XCircle aria-hidden="true" size={13} /> Passed: {labPassedCount} Attractions</span>
                <span className="preview-chip"><Globe aria-hidden="true" size={13} /> Real OSM Coordinates</span>
                <span className="preview-chip"><Sparkles aria-hidden="true" size={13} /> Showing Card {labSwipeIdx + 1} of {SWIPE_CANDIDATES.length}</span>
              </div>
            </div>
          )}

          {activeLabStep === 2 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 3: DETERMINISTIC OPTIMIZATION</div>
              <h5>Mixed-Integer Linear Programming (ILP) Solver & Route Matrix</h5>

              <div className="solver-route-flow">
                <div className="solver-node active">
                  <span className="node-time">09:00</span>
                  <span className="node-title">Hotel Base</span>
                </div>
                <div className="solver-edge">
                  <span>8m walk (550m)</span>
                </div>
                <div className="solver-node">
                  <span className="node-time">09:30</span>
                  <span className="node-title">{SWIPE_CANDIDATES[labSwipeIdx].name.split(" ")[0]}</span>
                </div>
                <div className="solver-edge">
                  <span>12m lunch</span>
                </div>
                <div className="solver-node">
                  <span className="node-time">12:15</span>
                  <span className="node-title">Lunch Window</span>
                </div>
                <div className="solver-edge">
                  <span>14m transit</span>
                </div>
                <div className="solver-node">
                  <span className="node-time">15:30</span>
                  <span className="node-title">Panoramic View</span>
                </div>
              </div>
              
              <div className="lab-solver-interactive">
                <button
                  className={`lab-solve-trigger ${labSolving ? "solving" : ""}`}
                  disabled={labSolving}
                  onClick={() => {
                    setLabSolving(true);
                    setTimeout(() => setLabSolving(false), 450);
                  }}
                  type="button"
                >
                  <Zap aria-hidden="true" size={16} />
                  {labSolving ? "Executing Mathematical Branch-and-Cut Solver..." : "⚡ Run Deterministic ILP Solver Benchmark"}
                </button>
                <div className="lab-solve-status">
                  <span className="solve-metric">⏱️ Solve Time: <strong>0.038s</strong></span>
                  <span className="solve-metric">📐 Constraints: <strong>544/544 Satisfied</strong></span>
                  <span className="solve-metric">🎯 Optimality Gap: <strong>0.00%</strong></span>
                </div>
              </div>

              <div className="preview-chips-row">
                <span className="preview-chip"><Timer aria-hidden="true" size={13} /> Three plan options in ~52s</span>
                <span className="preview-chip"><ShieldCheck aria-hidden="true" size={13} /> 0 Schedule Conflicts</span>
                <span className="preview-chip"><MapPinned aria-hidden="true" size={13} /> 100% Timezone Correct</span>
              </div>
            </div>
          )}

          {activeLabStep === 3 && (
            <div className="lab-preview-content">
              <div className="preview-tag">STAGE 4: EXECUTION & WORKBOOKS</div>
              <h5>Interactive Day Timelines + 6-Sheet Formatted Excel (.xlsx)</h5>
              
              <div className="lab-excel-tabs">
                {[
                  "1. ตารางเวลา (Timetable)",
                  "2. ค่าใช้จ่าย (Expenses & Split)",
                  "3. To-Do Checklist",
                  "4. Things to Bring",
                ].map((sheetName, idx) => (
                  <button
                    aria-pressed={labExcelTab === idx}
                    className={`lab-excel-tab ${labExcelTab === idx ? "active" : ""}`}
                    key={sheetName}
                    onClick={() => setLabExcelTab(idx)}
                    type="button"
                  >
                    <FileSpreadsheet aria-hidden="true" size={12} /> {sheetName}
                  </button>
                ))}
              </div>

              <div className="lab-excel-sheet-preview">
                {labExcelTab === 0 && (
                  <table className="mini-sheet-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Activity / Place</th>
                        <th>Leg Transit</th>
                        <th>Fatigue Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>09:30</td>
                        <td>Senso-ji Asakusa Pagoda</td>
                        <td>8 min walk (500m)</td>
                        <td><span className="sheet-tag-green">🌱 Fresh</span></td>
                      </tr>
                      <tr>
                        <td>12:15</td>
                        <td>Tsukiji Fresh Sushi Lunch</td>
                        <td>14 min transit</td>
                        <td><span className="sheet-tag-green">🍱 Reserved</span></td>
                      </tr>
                      <tr>
                        <td>15:30</td>
                        <td>Shibuya Sky Observatory</td>
                        <td>10 min walk (700m)</td>
                        <td><span className="sheet-tag-blue">⚡ Balanced</span></td>
                      </tr>
                    </tbody>
                  </table>
                )}

                {labExcelTab === 1 && (
                  <table className="mini-sheet-table">
                    <thead>
                      <tr>
                        <th>Item / Category</th>
                        <th>Paid By</th>
                        <th>Original ({splitCurrency})</th>
                        <th>Fair Share / Net</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Traditional Fado Dinner</td>
                        <td>Alex</td>
                        <td>{splitCurrency}120.00</td>
                        <td>Alex +{splitCurrency}45.00</td>
                      </tr>
                      <tr>
                        <td>Metro Passes &amp; Transit</td>
                        <td>Sam</td>
                        <td>{splitCurrency}60.00</td>
                        <td>Sam -{splitCurrency}15.00</td>
                      </tr>
                      <tr>
                        <td>Museum Gallery Entry</td>
                        <td>Jordan</td>
                        <td>{splitCurrency}45.00</td>
                        <td>Jordan -{splitCurrency}30.00</td>
                      </tr>
                    </tbody>
                  </table>
                )}

                {labExcelTab === 2 && (
                  <ul className="mini-checklist-items">
                    <li className="checked">✓ Verify passport validity (&gt;6 months remaining)</li>
                    <li className="checked">✓ Pre-load local IC transit cards on digital wallets</li>
                    <li className="checked">✓ Confirm dietary requirements for dinner reservations</li>
                  </ul>
                )}

                {labExcelTab === 3 && (
                  <ul className="mini-checklist-items">
                    <li className="checked">✓ Universal travel plug adapter &amp; charging brick</li>
                    <li className="checked">✓ Lightweight rain shell / packable umbrella</li>
                    <li className="checked">✓ Offline OpenStreetMap vector tiles cached</li>
                  </ul>
                )}
              </div>

              <div className="preview-chips-row">
                <span className="preview-chip"><FileSpreadsheet aria-hidden="true" size={13} /> Formatted Multi-Sheet .xlsx</span>
                <span className="preview-chip"><Wallet aria-hidden="true" size={13} /> Currency-Converted Expenses</span>
                <span className="preview-chip"><CalendarClock aria-hidden="true" size={13} /> Apple &amp; Google .ics Export</span>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* -------------------------------------------------------------
          SECTION 4: INTERACTIVE MULTI-CURRENCY BILL SPLIT SANDBOX
          ------------------------------------------------------------- */}
      <section className="landing-section split-sandbox-section" id="split-sandbox">
        <SceneBand />
        <SceneProp kind="luggageTag" place="tr" />
        <img
          alt=""
          aria-hidden="true"
          className="scene-art"
          loading="lazy"
          src="/illustrations/currency-conversion.svg"
        />
        <SceneProp kind="postcard" place="tl" />
        <div className="section-header">
          <span className="section-badge">
            <Calculator aria-hidden="true" size={13} /> {copy("landing_bullet_money", language)}
          </span>
          <h2>{copy("landing_split_sandbox_title", language)}</h2>
          <p className="section-lead">{copy("landing_split_sandbox_lead", language)}</p>
        </div>

        <div className="split-sandbox-card">
          {/* Quick Preset Selector & Currency Switcher */}
          <div className="split-sandbox-toolbar">
            <div className="split-currency-pills">
              {(["$", "€", "¥", "฿"] as const).map((curr) => (
                <button
                  aria-label={`${copy("landing_split_currency", language)} ${curr}`}
                  aria-pressed={splitCurrency === curr}
                  className={`curr-pill ${splitCurrency === curr ? "active" : ""}`}
                  key={curr}
                  onClick={() => setSplitCurrency(curr)}
                  type="button"
                >
                  {curr}
                </button>
              ))}
            </div>

            <div className="split-quick-presets">
              <span className="presets-label">Sample Bills:</span>
              <button
                className="split-preset-btn"
                onClick={() => {
                  setSampleBill1(120);
                  setSampleBill2(60);
                  setSampleBill3(45);
                }}
                type="button"
              >
                🍱 Dinner &amp; Transit
              </button>
              <button
                className="split-preset-btn"
                onClick={() => {
                  setSampleBill1(320);
                  setSampleBill2(180);
                  setSampleBill3(100);
                }}
                type="button"
              >
                🏖️ Beach Villa ({splitCurrency}600)
              </button>
              <button
                className="split-preset-btn"
                onClick={() => {
                  setSampleBill1(450);
                  setSampleBill2(450);
                  setSampleBill3(150);
                }}
                type="button"
              >
                🚄 Transit Passes ({splitCurrency}1,050)
              </button>
            </div>
          </div>

          <div className="split-sandbox-inputs">
            <div className="split-input-row">
              <label htmlFor="bill-1">
                <strong>Alex</strong> paid (Dinner &amp; Drinks):
              </label>
              <div className="input-affix">
                <span>{splitCurrency}</span>
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
                <strong>Sam</strong> paid (Taxi &amp; Train passes):
              </label>
              <div className="input-affix">
                <span>{splitCurrency}</span>
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
                <span>{splitCurrency}</span>
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
                <span className="split-val">{splitCurrency}{totalBill}</span>
              </div>
              <div className="split-stat">
                <span className="split-label">Fair Share / Person:</span>
                <span className="split-val">{splitCurrency}{perPerson}</span>
              </div>
            </div>

            <div className="split-transfers-box">
              <h6>
                <Zap aria-hidden="true" size={13} /> Minimal Settlement Transfers (0ms Math)
              </h6>
              <ul className="split-transfers-list">
                {jordanNet < 0 && (
                  <li>
                    <span className="transfer-flow">
                      <strong className="debtor">Jordan</strong>
                      <span className="flow-arrow">── owes {splitCurrency}{Math.abs(jordanNet)} ──▶</span>
                      <strong className="creditor">Alex</strong>
                    </span>
                  </li>
                )}
                {samNet < 0 && (
                  <li>
                    <span className="transfer-flow">
                      <strong className="debtor">Sam</strong>
                      <span className="flow-arrow">── owes {splitCurrency}{Math.abs(samNet)} ──▶</span>
                      <strong className="creditor">Alex</strong>
                    </span>
                  </li>
                )}
                {jordanNet >= 0 && samNet >= 0 && alexNet === 0 && (
                  <li className="all-settled">✓ All balances perfectly settled!</li>
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
        <SceneProp kind="boardingPass" place="bl" />
        <img
          alt=""
          aria-hidden="true"
          className="scene-art"
          loading="lazy"
          src="/illustrations/destination.svg"
        />
        <SceneProp kind="pin" place="tr" />
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
                <MapPinned aria-hidden="true" size={13} /> {p.city}, {p.country}
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
        <img alt="" aria-hidden="true" className="scene-art" loading="lazy" src="/illustrations/decide-night.svg" />
        <SceneProp kind="compass" place="tl" />
        <SceneProp kind="suitcase" place="tr" />
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
        <img alt="" aria-hidden="true" className="scene-art" loading="lazy" src="/illustrations/booking.svg" />
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
              <p className="landing-hint" id="destination-help">
                {copy("destination_help", language)}
              </p>

              <label htmlFor="country">
                <span>
                  {copy("country", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="landing-hint"> {copy("required_field", language)}</span>
                </span>
                <select
                  aria-describedby="destination-help"
                  autoComplete="country-name"
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
                  <span>
                    {copy("country", language)}
                    <span aria-hidden="true" className="setup-required">*</span>
                    <span className="landing-hint"> {copy("required_field", language)}</span>
                  </span>
                  <input
                    aria-describedby="destination-help"
                    autoFocus
                    autoCapitalize="words"
                    autoComplete="country-name"
                    autoCorrect="off"
                    id="country-custom"
                    name="country-custom"
                    onChange={(e) => setTypedCountry(e.target.value)}
                    placeholder={copy("country_placeholder", language)}
                    required
                    spellCheck={false}
                    type="text"
                    value={typedCountry}
                  />
                </label>
              )}

              {country !== TYPE_IT && cities.length > 0 ? (
                <label htmlFor="city">
                  <span>
                    {copy("city", language)}
                    <span aria-hidden="true" className="setup-required">*</span>
                    <span className="landing-hint"> {copy("required_field", language)}</span>
                  </span>
                  <select
                    aria-describedby="destination-help"
                    autoComplete="address-level2"
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
                  <span>
                    {copy("city", language)}
                    <span aria-hidden="true" className="setup-required">*</span>
                    <span className="landing-hint"> {copy("required_field", language)}</span>
                  </span>
                  <input
                    aria-describedby="destination-help"
                    autoCapitalize="words"
                    autoComplete="address-level2"
                    autoCorrect="off"
                    id="city-custom"
                    name="city-custom"
                    onChange={(e) => setTypedCity(e.target.value)}
                    placeholder={copy("city_placeholder", language)}
                    required
                    spellCheck={false}
                    type="text"
                    value={typedCity}
                  />
                </label>
              )}

              <label htmlFor="trip-name">
                {copy("trip_name", language)}
                <input
                  autoCapitalize="sentences"
                  autoComplete="off"
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
                aria-describedby={!resolvedCity ? "destination-required" : undefined}
                className="setup-primary"
                disabled={createTrip.isPending || !resolvedCity}
                type="submit"
              >
                {copy("start_planning", language)}
              </button>
              {!resolvedCity && (
                <p className="landing-hint" id="destination-required">
                  {copy("destination_required", language)}
                </p>
              )}
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
        <SceneBand flip />
        <SceneProp kind="stamp" place="br" />
        <img
          alt=""
          aria-hidden="true"
          className="scene-art"
          loading="lazy"
          src="/illustrations/all-checked.svg"
        />
        <SceneProp kind="plane" place="tl" />
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
                aria-controls={`faq-answer-${idx}`}
                aria-expanded={openFaq === idx}
                className="faq-question"
                id={`faq-question-${idx}`}
                onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
                type="button"
              >
                <span>{copy(item.q, language)}</span>
                <ChevronDown aria-hidden="true" className="faq-chevron" size={18} />
              </button>
              {/* Always rendered, collapsed by CSS rather than unmounted — an
                  answer that does not exist cannot animate open, and the
                  reference's accordion is one of the few places it spends
                  motion. `visibility` is transitioned to `hidden` at the end of
                  the collapse, which is what keeps a closed answer out of the
                  tab order and away from a screen reader. */}
              <div
                aria-labelledby={`faq-question-${idx}`}
                className="faq-answer"
                id={`faq-answer-${idx}`}
                role="region"
              >
                <div className="faq-answer-inner">
                  <p>{copy(item.a, language)}</p>
                </div>
              </div>
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
