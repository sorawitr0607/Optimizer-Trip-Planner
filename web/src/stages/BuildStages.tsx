import { Check, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { copy, type Language } from "../i18n/copy";
import { BUILD_STAGES } from "../shared/buildStages";

/**
 * What the build is doing, as the stages it actually goes through.
 *
 * `Thinking` rotates a line every few seconds and counts elapsed time, and it says in its
 * own comment why: "the server reports no milestones, so this claims none." That was true
 * of the *server*. It was never true of the client, which drives this build itself --
 * `autoResolveAndGenerate` awaits four separate calls in order, so each one resolving is
 * a fact the page already holds and was throwing away.
 *
 * So the stages here are marked done when their call returns, not on a timer. A green
 * check means that request came back. Nothing claims progress inside a stage except the
 * route count, which is the server's own tally of pairs measured, and the last stage --
 * one long `generate_plan_preview` that really has no milestones -- keeps `Thinking`
 * inside it, where a rotating line and an elapsed counter are the honest thing to show.
 *
 * derives-from: A2 day timeline as .build-stage -- no donor counterpart; the vertical
 * connector and the done/active/pending triple are the timeline's own shape reused for
 * progress rather than for time.
 */

export interface BuildStagesProps {
  language: Language;
  /** How many stages have returned. `0` means the first is in flight. */
  reached: number;
  /** Rendered inside the active stage — the elapsed counter on the long one. */
  children?: ReactNode;
  /** The server's count of route pairs measured so far, shown on the routes stage. */
  routesMeasured?: number;
}

export function BuildStages({ language, reached, children, routesMeasured }: BuildStagesProps) {
  return (
    <div aria-busy={reached < BUILD_STAGES.length} className="build-stages">
      <p className="build-stages-title">{copy("build_stages_title", language)}</p>
      <ol>
        {BUILD_STAGES.map((stage, index) => {
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
        <li className={`build-stage${reached >= BUILD_STAGES.length ? " done" : ""}`}>
          <span aria-hidden="true" className="build-stage-mark">
            <Check size={14} />
          </span>
          <span className="build-stage-body">
            <span className="build-stage-name">{copy("stage_complete", language)}</span>
            <span className="build-stage-detail">{copy("stage_complete_detail", language)}</span>
          </span>
        </li>
      </ol>
    </div>
  );
}
