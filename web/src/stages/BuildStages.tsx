import { Check, Loader2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { copy, copyFormat, type Language } from "../i18n/copy";
import { BUILD_STAGES, formatCountdown, remainingSeconds } from "../shared/buildStages";

/**
 * What the build is doing, as the stages it actually goes through.
 *
 * `Thinking` rotates a line every few seconds, and it says in its own comment why:
 * "the server reports no milestones, so this claims none." That was true
 * of the *server*. It was never true of the client, which drives this build itself --
 * `autoResolveAndGenerate` awaits four separate calls in order, so each one resolving is
 * a fact the page already holds and was throwing away.
 *
 * So the stages here are marked done when their call returns, not on a timer. A green
 * check means that request came back. Nothing claims progress inside a stage except the
 * route count, which is the server's own tally of pairs measured, and the last stage --
 * one long `generate_plan_preview` that really has no milestones -- keeps `Thinking`
 * inside it, where a rotating line and a realistic estimate are the honest thing to show.
 *
 * derives-from: A2 day timeline as .build-stage -- no donor counterpart; the vertical
 * connector and the done/active/pending triple are the timeline's own shape reused for
 * progress rather than for time.
 */

export interface BuildStagesProps {
  language: Language;
  /** Which list of stages to draw. Defaults to `/optimize`'s four. */
  stages?: readonly { key: string; icon: typeof Check; estimateSeconds: readonly [number, number] }[];
  /** How many stages have returned. `0` means the first is in flight. */
  reached: number;
  /** Rendered inside the active stage. */
  children?: ReactNode;
  /** The server's count of route pairs measured so far, shown on the routes stage. */
  routesMeasured?: number;
}

/**
 * The wait, counted down rather than stated.
 *
 * The estimate used to sit on every stage line as static text — four "Usually 5–15 sec"
 * rows under four names and four details, the same fact repeated where it is least
 * useful. It belongs on the progress bar, once, and it belongs *moving*: a range that
 * never changes says nothing about how far through you are.
 *
 * **This does not weaken the rule the rest of this file exists for.** A stage is still
 * marked done only when its call returns, and no stage or percentage advances on a
 * timer. The only thing the clock drives is the clock. It counts `remainingSeconds` —
 * the *ceiling* — and says "up to", so an ordinary build finishes with time still on it
 * rather than the counter hitting zero mid-build; past the ceiling it says it is taking
 * longer instead of sitting at 0:00, which would read as stuck.
 *
 * Its own component, mounted with `key={budget}`, because that makes remounting the
 * re-baseline: when a stage returns the budget changes and React starts a fresh counter
 * on the new number. Resetting state from inside an effect instead is what
 * `react-hooks/set-state-in-effect` exists to stop, and the effect here only subscribes
 * to a clock, which is what an effect is for.
 */
function Countdown({ language, seconds }: { language: Language; seconds: number }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    const tick = setInterval(
      () => setLeft((value) => (value > 0 ? value - 1 : 0)),
      1_000,
    );
    return () => clearInterval(tick);
  }, []);
  return (
    <span className="build-progress-left">
      {left > 0
        ? copyFormat("build_time_left", language, { clock: formatCountdown(left) })
        : copy("build_taking_longer", language)}
    </span>
  );
}

export function BuildStages({
  language,
  reached,
  children,
  routesMeasured,
  stages = BUILD_STAGES,
}: BuildStagesProps) {
  const budget = remainingSeconds(stages, reached);

  return (
    <div aria-busy={reached < stages.length} className="build-stages">
      <p className="build-stages-title">{copy("build_stages_title", language)}</p>
      <ol>
        {stages.map((stage, index) => {
          const done = index < reached;
          const active = index === reached;
          const Icon = done ? Check : active ? Loader2 : stage.icon;
          return (
            <li
              className={`build-stage${done ? " done" : ""}${active ? " active" : ""}`}
              key={stage.key}
            >
              <span aria-hidden="true" className="build-stage-mark">
                <Icon className={active ? "spin" : undefined} size={14} />
              </span>
              <span className="build-stage-body">
                <span className="build-stage-name">{copy(`stage_${stage.key}`, language)}</span>
                <span className="build-stage-detail">
                  {copy(`stage_${stage.key}_detail`, language)}
                </span>
                {/* Only where there is a real number to show. A stage that cannot count
                    says nothing rather than inventing a fraction. */}
                {active && stage.key === "routes" && routesMeasured ? (
                  <span className="build-stage-count">
                    {copy("routes_measured", language).replace("{n}", String(routesMeasured))}
                  </span>
                ) : null}
                {active ? children : null}
              </span>
            </li>
          );
        })}
        <li className={`build-stage${reached >= stages.length ? " done" : ""}`}>
          <span aria-hidden="true" className="build-stage-mark">
            <Check size={14} />
          </span>
          <span className="build-stage-body">
            <span className="build-stage-name">{copy("stage_complete", language)}</span>
            <span className="build-stage-detail">{copy("stage_complete_detail", language)}</span>
          </span>
        </li>
      </ol>
      <label className="build-progress">
        <span>
          {copyFormat("build_progress", language, {
            percent: Math.round(100 * Math.min(reached, stages.length) / stages.length),
          })}
          {/* Nothing at all once the build is done: a stopped clock beside "100%" is
              worse than no clock. `key={budget}` is the re-baseline — a stage returning
              changes the budget, which remounts the counter on the new one. */}
          {budget ? (
            <Countdown key={budget} language={language} seconds={budget} />
          ) : null}
        </span>
        <progress max={stages.length} value={Math.min(reached, stages.length)} />
      </label>
    </div>
  );
}
