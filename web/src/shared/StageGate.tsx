import { useQuery } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { Link, useParams } from "react-router";

import { rpc, type Journey, type StageKey } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

interface StageGateProps extends PropsWithChildren {
  stage: StageKey;
}

// derives-from: element 26 .recent-row-item
export function StageGate({ stage, children }: StageGateProps) {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const journey = useQuery({
    queryKey: ["journey", tripId],
    queryFn: () => rpc<Journey>("journey", { trip_id: tripId }),
    enabled: Boolean(tripId),
  });

  if (!tripId) return <p>{copy("journey_needs_trip", language)}</p>;
  if (journey.isPending) return <p>{copy("loading", language)}</p>;
  if (journey.isError) return <p>⚠ {journey.error.message}</p>;

  const blockedBy = journey.data.stages.find((item) => item.key === stage)?.blocked_by;
  if (!blockedBy) return children;

  return (
    <section className="stage-blocked" aria-live="polite">
      <h2>{copy("journey_blocked", language)}</h2>
      <p>{copy(`stage_${blockedBy}`, language)}</p>
      <Link className="primary-link" to={`/trips/${tripId}/${blockedBy}`}>
        {copy(`stage_${blockedBy}`, language)}
      </Link>
    </section>
  );
}
