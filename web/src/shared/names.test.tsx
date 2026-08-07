import { describe, expect, it } from "vitest";

import { mergeNames, placeAltName, placeName } from "./names";

/**
 * `WF-040` measured the reason this exists: 61% of the Taipei catalogue has no
 * OpenStreetMap `name:en`, so a card showed only 三玉宮 with nothing readable beside it.
 */
describe("place naming", () => {
  const osm = { name: "西門紅樓", names: { en: "Red House", local: "西門紅樓" } };
  const chineseOnly = { name: "三玉宮", names: { local: "三玉宮" } };

  it("shows the readable name first and the local one beside it", () => {
    expect(placeName(osm, "en")).toBe("Red House");
    expect(placeAltName(osm, "en")).toBe("西門紅樓");
  });

  it("never repeats the same name twice", () => {
    // Nothing to put beside it, so the card must print one name, not two identical ones.
    expect(placeName(chineseOnly, "en")).toBe("三玉宮");
    expect(placeAltName(chineseOnly, "en")).toBeNull();
  });

  it("takes a Wikidata label where OpenStreetMap has no English name", () => {
    const merged = mergeNames(chineseOnly, { en: "SanYu Temple" });

    expect(placeName(merged, "en")).toBe("SanYu Temple");
    expect(placeAltName(merged, "en")).toBe("三玉宮");
  });

  it("keeps the OpenStreetMap name when both sources have one", () => {
    // `name:en` is the name on the ground; the label is a reference name.
    const merged = mergeNames(osm, { en: "The Red House Theatre" });

    expect(placeName(merged, "en")).toBe("Red House");
  });

  it("ignores an empty label rather than blanking the name", () => {
    const merged = mergeNames(chineseOnly, { en: "" });

    expect(placeName(merged, "en")).toBe("三玉宮");
  });

  it("still shows both names in Thai", () => {
    const merged = mergeNames(chineseOnly, { en: "SanYu Temple" });

    // No Thai label, so English stands in — and the local name is still beside it.
    expect(placeName(merged, "th")).toBe("SanYu Temple");
    expect(placeAltName(merged, "th")).toBe("三玉宮");
  });
});
