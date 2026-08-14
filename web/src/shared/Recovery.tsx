import { isRouteErrorResponse, Link, useRouteError } from "react-router";

import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

/**
 * Where a wrong address or a broken screen lands.
 *
 * Three states shared one dead end before this: a mistyped URL got React Router's own
 * "Unexpected Application Error! 404 Not Found", which is a *development* page and reads
 * as the product being unfinished; a deleted or mistyped trip id rendered the whole setup
 * wizard and only admitted `unknown_trip` after the owner had re-entered their answers;
 * and a thrown render error took the screen out with nothing to press.
 *
 * All three now say what happened in the app's own voice and offer the two ways out that
 * always exist. Deliberately not a redirect: silently moving someone somewhere else hides
 * the fact that their bookmark is stale, and they would hit it again tomorrow.
 */

/* derives-from: element 36 .currency-info-box as .recovery. Same recessed panel and
   border treatment as every other "here is the situation" block on the stage screens;
   only the centring is its own, because this is the whole screen rather than part of one. */

export interface RecoveryProps {
  title: string;
  body: string;
  /** Shown under the two standing actions, for a code worth quoting in a bug report. */
  detail?: string | null;
}

export function Recovery({ title, body, detail }: RecoveryProps) {
  const { language } = useLanguage();
  return (
    <main className="stage-card recovery">
      <h1>{title}</h1>
      <p>{body}</p>
      <div className="recovery-actions">
        <Link className="setup-primary" to="/trips">
          {copy("back_to_trips", language)}
        </Link>
      </div>
      {detail ? <p className="setup-hint recovery-detail">{detail}</p> : null}
    </main>
  );
}

/** The router's `errorElement`: a thrown render error, and the catch-all 404. */
export function RouteError() {
  const { language } = useLanguage();
  const error = useRouteError();
  const missing = isRouteErrorResponse(error) && error.status === 404;
  return (
    <Recovery
      body={copy(missing ? "not_found_body" : "app_error_body", language)}
      detail={
        isRouteErrorResponse(error)
          ? `${error.status} ${error.statusText}`
          : error instanceof Error
            ? error.message
            : null
      }
      title={copy(missing ? "not_found_title" : "app_error_title", language)}
    />
  );
}
