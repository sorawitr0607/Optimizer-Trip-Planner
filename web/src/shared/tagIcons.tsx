import {
  Armchair, Baby, Banknote, Bath, BedDouble, Bell, Bike, Binoculars, Building, Building2,
  Bus, CalendarCheck, Camera, ClipboardList, Clock, Coffee, Drama, FerrisWheel, Fingerprint,
  Flower2, Footprints, Gavel, HeartPulse, Hourglass, Landmark, Luggage, Map, Moon, MoreHorizontal,
  Mountain, MountainSnow, Palette, PawPrint, PersonStanding, ReceiptText, Scale, ScrollText,
  ShoppingBag, Siren, Soup, Stamp, Store, Ticket, TrainFront, Trees, TriangleAlert, Users,
  Utensils, Waves, Wifi,
} from "lucide-react";

/**
 * One glyph per trip-style tag.
 *
 * `/setup` step 3 asks four questions with 34 chips between them, and a chip is
 * read by scanning rather than by reading — a wall of same-shaped words is slow
 * in a way that is nobody's fault and easy to fix. The glyph is a second channel
 * on the word, never a replacement: every chip still carries its full
 * `TAG_TEXT` label, and the icon is `aria-hidden` wherever it is drawn.
 *
 * Two rules held while choosing them, both of which cost a candidate:
 *
 * - **A wrong icon is worse than none**, because it teaches an association the
 *   app then has to undo. Anything merely decorative was dropped rather than
 *   guessed at.
 * - **`religious_sites` is `Bell`, not `Church`.** The label is "Temples &
 *   shrines" and the pilot destination is Taipei; lucide has `Church`, `Mosque`
 *   and no torii or pagoda, so a neutral glyph common to all of them is the
 *   honest choice. `Landmark` was taken by `culture` and is the fallback below.
 *
 * The table is exhaustive by test — `tagIcons.test.tsx` asserts every code in
 * `TAG_TEXT` has an entry and that none is spare, so a new tag cannot ship
 * silently iconless.
 */
export const TAG_ICONS = {
  activity: Bike,
  animals: PawPrint,
  architecture: Building2,
  art: Palette,
  balanced_pace: Scale,
  chill: Coffee,
  culture: Landmark,
  family: Baby,
  heavy_crowds: Users,
  history: ScrollText,
  late_meals: Soup,
  local_street_food: Utensils,
  long_queues: Hourglass,
  low_walking: PersonStanding,
  malls: Building,
  markets: Store,
  meal_on_time: Clock,
  nature: Trees,
  neighborhoods: Map,
  night_view: Moon,
  parks_gardens: Flower2,
  performing_arts: Drama,
  photography: Camera,
  plain_long_walks: Footprints,
  religious_sites: Bell,
  rest_breaks: Armchair,
  rewarding_walks: Mountain,
  shopping: ShoppingBag,
  sightseeing: Binoculars,
  theme_parks: FerrisWheel,
  tourist_traps: TriangleAlert,
  views: MountainSnow,
  water: Waves,
  wellness: Bath,
} as const satisfies Record<string, typeof Bike>;

/**
 * The glyph for a tag, or `Landmark` for one this table has not met.
 *
 * A fallback rather than nothing, so a tag added to the catalogue before this
 * table renders as a chip with a neutral mark instead of one chip that is
 * visibly shorter than its neighbours. The test is what stops the fallback
 * quietly becoming the answer.
 */
export function tagIcon(code: string): typeof Bike {
  return (TAG_ICONS as Record<string, typeof Bike>)[code] ?? Landmark;
}

/**
 * The readiness board's categories, which are `checklist.CATEGORIES` in Python.
 *
 * Same reasoning as the tags: a filter row is scanned, not read. Different table
 * because it is a different vocabulary — reusing a glyph across the two is fine
 * and expected, since a chip is only ever read among its own kind.
 *
 * `tests/test_icon_tables.py` is what keeps this honest: a TypeScript test cannot
 * read a Python tuple, so the coverage check lives on the Python side and fails
 * when a category is added there without a glyph here.
 */
export const CHECKLIST_ICONS = {
  accommodation: BedDouble,
  connectivity: Wifi,
  emergency: Siren,
  entry_requirements: Stamp,
  immigration_customs: Fingerprint,
  insurance_health: HeartPulse,
  local_rules: Gavel,
  money: Banknote,
  packing: Luggage,
  registrations: ClipboardList,
  reservations: CalendarCheck,
  transport_setup: TrainFront,
} as const satisfies Record<string, typeof Bike>;

/** The expense categories, which are `costs.CATEGORIES` in Python. */
export const COST_ICONS = {
  accommodation: BedDouble,
  activity: Ticket,
  fees: ReceiptText,
  food: Utensils,
  other: MoreHorizontal,
  shopping: ShoppingBag,
  transport: Bus,
} as const satisfies Record<string, typeof Bike>;

/** The glyph for a readiness category, or a neutral mark for an unknown one. */
export function checklistIcon(code: string): typeof Bike {
  return (CHECKLIST_ICONS as Record<string, typeof Bike>)[code] ?? ClipboardList;
}

/** The glyph for an expense category, or a neutral mark for an unknown one. */
export function costIcon(code: string): typeof Bike {
  return (COST_ICONS as Record<string, typeof Bike>)[code] ?? MoreHorizontal;
}
