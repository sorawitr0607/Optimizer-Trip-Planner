import { describe, expect, it } from "vitest";

import { mergeNames, placeName, placeNameFrom } from "./names";

/**
 * `WF-040` measured the reason this exists: 61% of the Taipei catalogue has no
 * OpenStreetMap `name:en`, so a card showed only 三玉宮 with nothing readable beside it.
 */
describe("place naming", () => {
  const osm = { name: "西門紅樓", names: { en: "Red House", local: "西門紅樓" } };
  const chineseOnly = { name: "三玉宮", names: { local: "三玉宮" } };

  it("shows the sourced English name in either interface language", () => {
    expect(placeName(osm, "en")).toBe("Red House");
    expect(placeName({ ...osm, names: { ...osm.names, th: "โรงละครเรดเฮาส์" } }, "th")).toBe("Red House");
  });

  it("keeps the sourced literal when no English name exists", () => {
    expect(placeName(chineseOnly, "en")).toBe("三玉宮");
  });

  it("takes a Wikidata label where OpenStreetMap has no English name", () => {
    const merged = mergeNames(chineseOnly, { en: "SanYu Temple" });

    expect(placeName(merged, "en")).toBe("SanYu Temple");
  });

  it("keeps the OpenStreetMap name when both sources have one", () => {
    // `name:en` is the name on the ground; the label is a reference name.
    const merged = mergeNames(osm, { en: "The Red House Theatre" });

    expect(placeName(merged, "en")).toBe("Red House");
  });

  it("ignores an empty label rather than blanking the name", () => {
    const merged = mergeNames(chineseOnly, { en: "" });

    expect(placeName(merged, "en")).toBe("三玉宮");
    expect(placeName(mergeNames({ name: "三玉宮", names: { en: "" } }, { en: "SanYu Temple" }), "en")).toBe("SanYu Temple");
  });

  it("uses English in frozen itinerary rows", () => {
    const merged = mergeNames(chineseOnly, { en: "SanYu Temple" });

    expect(placeName(merged, "th")).toBe("SanYu Temple");
    expect(placeNameFrom({ name: "西門紅樓", names: { en: "Red House", th: "โรงละครเรดเฮาส์" } }, "th")).toBe("Red House");
  });
});
