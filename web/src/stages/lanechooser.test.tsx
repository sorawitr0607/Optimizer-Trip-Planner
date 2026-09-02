import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../i18n/LanguageProvider";
import { laneAlreadyChosen, rememberLaneChoice } from "../shared/laneChoice";
import { LaneChooser } from "./LaneChooser";

const LANES = ["main_queue", "city_icons", "worth_it_if"];

function render(picked: string[] = []) {
  return renderToStaticMarkup(
    <LanguageProvider initial="en">
      <LaneChooser
        countOf={(lane) => ({ main_queue: 41, city_icons: 431, worth_it_if: 7 })[lane] ?? 0}
        language="en"
        lanes={LANES}
        onPick={(lane) => picked.push(lane)}
      />
    </LanguageProvider>,
  );
}

/** Enough of `localStorage` to be written to and read back, plus a locked-down one. */
function storage(locked = false) {
  const held = new Map<string, string>();
  return {
    getItem: (key: string) => {
      if (locked) throw new Error("denied");
      return held.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (locked) throw new Error("denied");
      held.set(key, value);
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("LaneChooser", () => {
  it("asks the question and describes every lane it offers", () => {
    const html = render();

    expect(html).toContain("Where would you like to start?");
    // The half the lane tabs were missing: a name and a count say nothing about what
    // "Worth It If…" holds, which is why the choice was worth asking for.
    expect(html).toContain("City Icons");
    expect(html).toContain("The places the city is known for");
    expect(html).toContain("Good, but only with the right timing or effort");
    expect(html).toContain("431");
  });

  it("offers a way past the question", () => {
    // Starting on the first lane is exactly what the screen did on its own, so an owner
    // who does not want to choose must not be blocked by the choice.
    expect(render()).toContain("Just start with For your trip");
  });

  it("draws only the lanes it was given", () => {
    const html = render();

    // `availableLanes` has already dropped the empty ones; an offer with no cards
    // behind it would be a dead button.
    expect(html).not.toContain("Browse All");
    expect(html).not.toContain("Local Alternatives");
  });
});

describe("laneAlreadyChosen", () => {
  it("is false until the run has been answered, and true after", () => {
    vi.stubGlobal("localStorage", storage());
    expect(laneAlreadyChosen("run-1")).toBe(false);
    rememberLaneChoice("run-1");
    expect(laneAlreadyChosen("run-1")).toBe(true);
  });

  it("keys on the run, so a fresh search asks again", () => {
    // The trigger is "after finish load", and a new discovery run is a new set of
    // lanes with new counts — answering the last one must not answer this one.
    vi.stubGlobal("localStorage", storage());
    rememberLaneChoice("run-1");
    expect(laneAlreadyChosen("run-2")).toBe(false);
  });

  it("stays quiet in a capture, where every profile is a first visit", () => {
    // `environment: "node"`, so there is no document to set a flag on — stubbed to the
    // one thing the check reads. Without this seam every `/places` screen baseline would
    // photograph the panel instead of the deck it is watching.
    vi.stubGlobal("localStorage", storage());
    vi.stubGlobal("document", { documentElement: { dataset: { capture: "1" } } });
    expect(laneAlreadyChosen("run-3")).toBe(true);
  });

  it("treats a profile that refuses storage as already answered", () => {
    // A panel is not worth a thrown error on a locked-down profile; reading as
    // "answered" means the deck simply deals, which is the old behaviour.
    vi.stubGlobal("localStorage", storage(true));
    expect(laneAlreadyChosen("run-4")).toBe(true);
    expect(() => rememberLaneChoice("run-4")).not.toThrow();
  });
});
