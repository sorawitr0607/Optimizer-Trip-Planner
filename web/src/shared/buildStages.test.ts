import { describe, expect, it } from "vitest";

import {
  BUILD_STAGES,
  PLAN_STAGES,
  formatCountdown,
  remainingSeconds,
  type BuildStage,
} from "./buildStages";

describe("remainingSeconds", () => {
  it("sums the ceilings of the stages that have not returned", () => {
    // The ceiling, not the midpoint: this number is counted down on screen, and a
    // clock that reaches zero while the build carries on is a broken promise.
    const total = BUILD_STAGES.reduce((sum, stage) => sum + stage.estimateSeconds[1], 0);
    expect(remainingSeconds(BUILD_STAGES as readonly BuildStage[], 0)).toBe(total);
    expect(remainingSeconds(PLAN_STAGES as readonly BuildStage[], 2)).toBe(90 + 120);
  });

  it("is zero once everything has returned, so nothing is drawn", () => {
    expect(remainingSeconds(BUILD_STAGES as readonly BuildStage[], BUILD_STAGES.length)).toBe(0);
    // And past the end, which `reached` can reach on the completion row.
    expect(remainingSeconds(BUILD_STAGES as readonly BuildStage[], 99)).toBe(0);
  });

  it("treats a negative count as the start rather than reading backwards", () => {
    expect(remainingSeconds(PLAN_STAGES as readonly BuildStage[], -3)).toBe(
      remainingSeconds(PLAN_STAGES as readonly BuildStage[], 0),
    );
  });
});

describe("formatCountdown", () => {
  it("zero-pads the seconds so the width does not jump", () => {
    expect(formatCountdown(65)).toBe("1:05");
    expect(formatCountdown(9)).toBe("0:09");
    expect(formatCountdown(600)).toBe("10:00");
  });

  it("grows an hours field only when there is one", () => {
    expect(formatCountdown(3599)).toBe("59:59");
    expect(formatCountdown(3600)).toBe("1:00:00");
    expect(formatCountdown(3661)).toBe("1:01:01");
  });

  it("never shows a negative clock", () => {
    // The counter stops at zero and the caller swaps in "taking longer than usual",
    // but the formatter must not be the thing that decides that.
    expect(formatCountdown(0)).toBe("0:00");
    expect(formatCountdown(-30)).toBe("0:00");
  });
});
