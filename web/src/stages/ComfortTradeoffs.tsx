import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { rpc, type ComfortTradeoffReport } from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";

/**
 * Agreeing to exceed one comfort budget. `WF-039`.
 *
 * The escape hatch existed in `validate_variant` and was unreachable: no call site ever
 * produced the `fits_with_tradeoff` status it keyed on, and `owner_acceptance_required`
 * was set to exactly the condition that had to be false. So an owner two minutes over a
 * 25-minute cap could only abandon the plan or drop the cap for the whole trip.
 *
 * **The button carries the number.** It reads "Agree to 27 min", not "Accept", and the
 * value is sent with the request, because an acceptance recorded as a yes would go on
 * applying to whatever a later replan produced. When the plan gets worse than what was
 * agreed, the row says so and asks again rather than quietly staying green.
 */

export interface ComfortTradeoffsProps {
  tripId: string;
  language: Language;
}

export function ComfortTradeoffs({ tripId, language }: ComfortTradeoffsProps) {
  const queryClient = useQueryClient();
  const report = useQuery({
    queryKey: ["comfort_tradeoffs", tripId],
    queryFn: () => rpc<ComfortTradeoffReport>("comfort_tradeoffs", { trip_id: tripId }),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["comfort_tradeoffs", tripId] });
    await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
  };

  const accept = useMutation({
    mutationFn: (input: { code: string; value: number }) =>
      rpc<unknown>("accept_comfort_tradeoff", {
        trip_id: tripId,
        code: input.code,
        value: input.value,
      }),
    onSuccess: refresh,
  });
  const withdraw = useMutation({
    mutationFn: (code: string) =>
      rpc<unknown>("withdraw_comfort_tradeoff", { trip_id: tripId, code }),
    onSuccess: refresh,
  });

  if (report.isPending || report.isError) return null;
  const rules = report.data.rules.filter(
    (rule) => rule.threshold !== null && (rule.exceeds || rule.accepted_value !== null),
  );
  if (!rules.length) return null;

  return (
    <section className="comfort-tradeoffs">
      <h3>{copy("comfort_tradeoffs", language)}</h3>
      <p className="setup-hint">{copy("comfort_tradeoffs_hint", language)}</p>
      {report.data.has_plan ? null : (
        <p className="setup-hint">{copy("comfort_needs_a_plan", language)}</p>
      )}
      <ul className="comfort-rule-list">
        {rules.map((rule) => (
          // derives-from: element 26 .recent-row-item as .comfort-rule
          <li className="comfort-rule" key={rule.code}>
            <div>
              <strong>{copyFrom("OPTIMIZER_CODE_TEXT", rule.code, language)}</strong>
              <p className="setup-hint">
                {rule.measured === null || rule.threshold === null
                  ? copy("comfort_no_limit_set", language)
                  : rule.exceeds
                    ? copyFormat("comfort_over_limit", language, {
                        measured: String(rule.measured),
                        threshold: String(rule.threshold),
                      })
                    : copy("comfort_within_limit", language)}
              </p>
              {rule.accepted_value === null ? null : (
                <p className="setup-hint">
                  {rule.covered || !rule.exceeds
                    ? copyFormat("comfort_agreed_to", language, {
                        value: String(rule.accepted_value),
                      })
                    : // Agreed to less than the plan now asks for. Saying so is the
                      // whole point of storing the number rather than a boolean.
                      copyFormat("comfort_agreed_but_stale", language, {
                        value: String(rule.accepted_value),
                        measured: String(rule.measured ?? 0),
                      })}
                </p>
              )}
            </div>
            <div className="place-choice-actions">
              {rule.exceeds && !rule.covered && rule.measured !== null ? (
                <button
                  disabled={accept.isPending}
                  onClick={() => accept.mutate({ code: rule.code, value: rule.measured! })}
                  type="button"
                >
                  {copyFormat("accept_this_amount", language, {
                    measured: String(rule.measured),
                  })}
                </button>
              ) : null}
              {rule.accepted_value === null ? null : (
                <button
                  disabled={withdraw.isPending}
                  onClick={() => withdraw.mutate(rule.code)}
                  type="button"
                >
                  {copy("withdraw_agreement", language)}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
