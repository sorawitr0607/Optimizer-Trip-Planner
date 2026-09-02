import { copy, copyFormat, type Language } from "../i18n/copy";

/**
 * Which list to work through first, asked once when the places arrive.
 *
 * `/places` finishes a 30-90 second search and lands the owner straight on the first
 * card of whichever lane happened to be active, with the lane tabs above it as five
 * names and five counts and nothing saying what any of them mean. The lanes are the
 * screen's most useful control and the least legible one — "Worth It If…" and "For your
 * trip" do not explain themselves — so the first decision the app asks for is a swipe on
 * a card it chose, rather than a choice about what kind of place to look at.
 *
 * So the deck waits, once, behind this. Each lane is a button carrying its name, how many
 * places are in it, and one line on what it holds.
 *
 * Asked once per discovery run: see `shared/laneChoice`, which also explains why this
 * never appears in a screen capture.
 *
 * derives-from: A4 ranked candidate card as .lane-chooser-option — no donor counterpart;
 * Auto-Bill has two screens and neither ranks anything, so this reuses the shape
 * `/places` already gives a ranked card carrying a name, a count and a line of prose.
 */

export interface LaneChooserProps {
  language: Language;
  /** The lanes that actually hold cards, in the order the tabs show them. */
  lanes: readonly string[];
  countOf: (lane: string) => number;
  onPick: (lane: string) => void;
}

export function LaneChooser({ language, lanes, countOf, onPick }: LaneChooserProps) {
  return (
    <section className="lane-chooser">
      <h2 className="money-eyebrow">{copy("lane_choose_title", language)}</h2>
      <p className="setup-hint">{copy("lane_choose_hint", language)}</p>
      <div className="lane-chooser-options">
        {lanes.map((lane) => (
          <button
            className="lane-chooser-option"
            key={lane}
            onClick={() => onPick(lane)}
            type="button"
          >
            <span className="lane-chooser-name">
              {copy(lane, language)}
              <span className="lane-tab-count">{countOf(lane)}</span>
            </span>
            {/* What the lane holds. The tabs carry the name and the count already; this
                is the half that was missing, and it is why the choice is worth asking. */}
            <span className="lane-chooser-detail">
              {copy(`${lane}_detail`, language)}
            </span>
          </button>
        ))}
      </div>
      {/* Not a wall: an owner who does not want to choose should not have to. Picking the
          first lane is exactly what the screen used to do on its own. */}
      <button
        className="lane-chooser-skip"
        onClick={() => onPick(lanes[0] ?? "main_queue")}
        type="button"
      >
        {copyFormat("lane_choose_skip", language, {
          lane: copy(lanes[0] ?? "main_queue", language),
        })}
      </button>
    </section>
  );
}
