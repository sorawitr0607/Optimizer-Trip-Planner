import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type SetupDraft,
  type SetupVocabulary,
  type Trip,
} from "../api/client";
import { copy, copyFormat, copyFrom } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

const STEP_COUNT = 5;
const STEP_TITLES = ["trip_basics", "owner_style", "travellers", "requirements", "review"];
// A POC view convention, not a core rule: setup.py accepts any number.
const MAX_MEMBERS = 8;

interface Member {
  traveller_id: string;
  label: string;
  age: number | null;
  tags: string[];
  description: string;
  must_respect: string[];
  nationality: string | null;
}

/**
 * Every `save_setup` argument in one object.
 *
 * It is always sent whole. `save_setup` defaults every field to empty, so a
 * partial payload silently erases what it omits -- which is why five steps are
 * five views over one piece of state rather than five requests.
 */
interface Draft {
  start_date: string | null;
  end_date: string | null;
  arrival_time: string | null;
  departure_time: string | null;
  accommodation_status: string;
  owner_age: number | null;
  main_style: string[];
  also_enjoy: string[];
  avoid: string[];
  comfort: string[];
  owner_description: string;
  owner_must_respect: string;
  owner_nationality: string | null;
  travellers: Member[];
}

const EMPTY: Draft = {
  start_date: null,
  end_date: null,
  arrival_time: null,
  departure_time: null,
  accommodation_status: "unknown",
  owner_age: null,
  main_style: [],
  also_enjoy: [],
  avoid: [],
  comfort: [],
  owner_description: "",
  owner_must_respect: "",
  owner_nationality: null,
  travellers: [],
};

/** Map a stored payload back into form values, losing no field on the way. */
function toDraft(record: SetupDraft | null): Draft {
  const payload = record?.snapshot.data;
  if (!payload) return EMPTY;
  const owner = payload.owner ?? {};
  const basics = payload.trip_basics ?? {};
  return {
    start_date: basics.start_date ?? null,
    end_date: basics.end_date ?? null,
    arrival_time: basics.arrival_time ?? null,
    departure_time: basics.departure_time ?? null,
    accommodation_status: basics.accommodation_status ?? "unknown",
    owner_age: owner.age ?? null,
    main_style: owner.main_style ?? [],
    also_enjoy: owner.also_enjoy ?? [],
    avoid: owner.avoid ?? [],
    comfort: owner.comfort ?? [],
    owner_description: owner.description ?? "",
    owner_must_respect: (owner.must_respect ?? []).join("\n"),
    // The POC's save drops both nationalities, so a round-trip through it
    // erases them. Carrying them here is what makes the draft whole.
    owner_nationality: owner.nationality ?? null,
    travellers: (payload.travellers ?? []).map((member) => ({
      traveller_id: member.traveller_id,
      label: member.label ?? "",
      age: member.age ?? null,
      tags: member.tags ?? [],
      description: member.description ?? "",
      must_respect: member.must_respect ?? [],
      nationality: member.nationality ?? null,
    })),
  };
}

export function SetupPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [flash, setFlash] = useState<{ tone: "ok" | "bad"; code: string } | null>(null);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const stored = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });
  const vocabulary = useQuery({
    queryKey: ["setup_vocabulary"],
    queryFn: () => rpc<SetupVocabulary>("setup_vocabulary"),
    staleTime: Infinity,
  });

  const save = useMutation({
    mutationFn: (input: { values: Draft; confirmed: boolean }) =>
      rpc<SetupDraft>("save_setup", {
        trip_id: tripId,
        ...input.values,
        travellers: input.values.travellers.map((member) => ({
          ...member,
          age: member.age ?? 0,
        })),
        confirmed: input.confirmed,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["setup", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
    },
  });

  if (stored.isPending || vocabulary.isPending) return <p>{copy("loading", language)}</p>;
  if (stored.isError) return <p className="field-error">⚠ {stored.error.message}</p>;
  if (vocabulary.isError) return <p className="field-error">⚠ {vocabulary.error.message}</p>;

  const values = draft ?? toDraft(stored.data);
  const confirmed = Boolean(stored.data?.confirmed);
  const trip = trips.data?.find((item) => item.trip_id === tripId);
  const words = vocabulary.data;

  function edit(patch: Partial<Draft>) {
    setDraft({ ...values, ...patch });
    setFlash(null);
  }

  function toggle(field: "main_style" | "also_enjoy" | "avoid" | "comfort", code: string) {
    const current = values[field];
    edit({
      [field]: current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code],
    } as Partial<Draft>);
  }

  // Nothing typed is lost by navigating: every move saves the open step first.
  async function go(target: number, options: { confirm?: boolean } = {}) {
    if (options.confirm && values.main_style.length === 0) {
      setFlash({ tone: "bad", code: "main_required" });
      return;
    }
    try {
      await save.mutateAsync({ values, confirmed: options.confirm || confirmed });
      if (options.confirm) {
        navigate(`/trips/${tripId}/places`);
        return;
      }
      setFlash({ tone: "ok", code: "step_saved" });
      setStep(Math.min(Math.max(target, 1), STEP_COUNT));
    } catch (error) {
      setFlash({
        tone: "bad",
        code: error instanceof ApiError ? error.code : String(error),
      });
    }
  }

  function setMemberCount(count: number) {
    const next = Array.from({ length: count }, (_, index) => (
      values.travellers[index] ?? {
        traveller_id: `member_${index + 1}`,
        label: "",
        age: null,
        tags: [],
        description: "",
        must_respect: [],
        nationality: null,
      }
    ));
    edit({ travellers: next });
  }

  function editMember(index: number, patch: Partial<Member>) {
    edit({
      travellers: values.travellers.map((member, at) =>
        at === index ? { ...member, ...patch } : member,
      ),
    });
  }

  return (
    <section className="stage-card setup-screen">
      <header className="money-head">
        <h1>{copy("setup", language)}</h1>
        <p>{copy("setup_help", language)}</p>
      </header>

      {/* derives-from: element 7 .wizard-progress-4 as .wizard-steps, generalised to five steps
          because the donor's class family hardcodes four. */}
      <ol className="wizard-steps">
        {STEP_TITLES.map((title, index) => {
          const number = index + 1;
          const reached = number <= step;
          return (
            <li
              className={`wizard-step${number === step ? " current" : ""}${
                reached ? " reached" : ""
              }`}
              key={title}
            >
              {/* Backwards only. Later steps depend on earlier answers, so this
                  suits the wizard rather than being a limitation to fix. */}
              <button
                disabled={number >= step}
                onClick={() => go(number)}
                type="button"
              >
                <span className="wizard-step-num">{number}</span>
                <span className="wizard-step-label">{copy(title, language)}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="wizard-count">
        {copyFormat("step_of", language, { current: step, total: STEP_COUNT })}
        {confirmed ? ` · ${copy("confirmed", language)}` : ` · ${copy("draft", language)}`}
      </p>

      {flash ? (
        <p className={flash.tone === "ok" ? "setup-flash" : "field-error"} aria-live="polite">
          {copy(flash.code, language)}
        </p>
      ) : null}

      {step === 1 ? (
        <div className="setup-fields">
          <label className="setup-check">
            <input
              checked={values.start_date !== null}
              onChange={(event) =>
                edit(
                  event.target.checked
                    ? { start_date: "", end_date: "" }
                    : { start_date: null, end_date: null },
                )
              }
              type="checkbox"
            />
            {copy("dates_known", language)}
          </label>
          {values.start_date === null ? (
            <p className="setup-hint">{copy("no_dates", language)}</p>
          ) : (
            <>
              <label>
                {copy("start_date", language)}
                <input
                  onChange={(event) => edit({ start_date: event.target.value })}
                  type="date"
                  value={values.start_date}
                />
              </label>
              <label>
                {copy("end_date", language)}
                <input
                  onChange={(event) => edit({ end_date: event.target.value })}
                  type="date"
                  value={values.end_date ?? ""}
                />
              </label>
            </>
          )}
          <label className="setup-check">
            <input
              checked={values.arrival_time !== null}
              onChange={(event) =>
                edit({ arrival_time: event.target.checked ? "17:00" : null })
              }
              type="checkbox"
            />
            {copy("arrival_known", language)}
          </label>
          {values.arrival_time === null ? null : (
            <label>
              {copy("arrival_time", language)}
              <input
                onChange={(event) => edit({ arrival_time: event.target.value })}
                type="time"
                value={values.arrival_time}
              />
            </label>
          )}
          <label className="setup-check">
            <input
              checked={values.departure_time !== null}
              onChange={(event) =>
                edit({ departure_time: event.target.checked ? "11:00" : null })
              }
              type="checkbox"
            />
            {copy("departure_known", language)}
          </label>
          {values.departure_time === null ? null : (
            <label>
              {copy("departure_time", language)}
              <input
                onChange={(event) => edit({ departure_time: event.target.value })}
                type="time"
                value={values.departure_time}
              />
            </label>
          )}
          <label>
            {copy("accommodation", language)}
            <select
              onChange={(event) => edit({ accommodation_status: event.target.value })}
              value={values.accommodation_status}
            >
              {words.accommodation_statuses.map((status) => (
                <option key={status} value={status}>
                  {copyFrom("ACCOMMODATION_TEXT", status, language)}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="setup-fields">
          {(["main_style", "also_enjoy", "avoid", "comfort"] as const).map((group) => (
            <fieldset className="setup-tags" key={group}>
              <legend>
                {copy(group, language)}
                {group === "main_style" ? " *" : ""}
              </legend>
              {words.tag_groups[group].map((code) => (
                <button
                  aria-pressed={values[group].includes(code)}
                  className="money-chip"
                  key={code}
                  onClick={() => toggle(group, code)}
                  type="button"
                >
                  {copyFrom("TAG_TEXT", code, language)}
                </button>
              ))}
            </fieldset>
          ))}
          <label>
            {copy("owner_age", language)}
            <input
              max={120}
              min={0}
              onChange={(event) =>
                edit({ owner_age: event.target.value ? Number(event.target.value) : null })
              }
              type="number"
              value={values.owner_age ?? ""}
            />
          </label>
          <label className="setup-wide">
            {copy("description", language)}
            <textarea
              onChange={(event) => edit({ owner_description: event.target.value })}
              rows={3}
              value={values.owner_description}
            />
          </label>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="setup-fields">
          <label>
            {copy("member_count", language)}
            <input
              max={MAX_MEMBERS}
              min={0}
              onChange={(event) =>
                setMemberCount(Math.min(Number(event.target.value || 0), MAX_MEMBERS))
              }
              type="number"
              value={values.travellers.length}
            />
          </label>
          {values.travellers.map((member, index) => (
            <fieldset className="setup-member setup-wide" key={member.traveller_id}>
              <legend>{member.traveller_id}</legend>
              <label>
                {copy("member_name", language)}
                <input
                  onChange={(event) => editMember(index, { label: event.target.value })}
                  value={member.label}
                />
              </label>
              <label>
                {copy("member_age", language)}
                <input
                  max={120}
                  min={0}
                  onChange={(event) =>
                    editMember(index, {
                      age: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  type="number"
                  value={member.age ?? ""}
                />
              </label>
              <div className="setup-tags">
                <span className="setup-legend">{copy("member_tags", language)}</span>
                {words.tag_groups.also_enjoy.concat(words.tag_groups.comfort).map((code) => (
                  <button
                    aria-pressed={member.tags.includes(code)}
                    className="money-chip"
                    key={code}
                    onClick={() =>
                      editMember(index, {
                        tags: member.tags.includes(code)
                          ? member.tags.filter((item) => item !== code)
                          : [...member.tags, code],
                      })
                    }
                    type="button"
                  >
                    {copyFrom("TAG_TEXT", code, language)}
                  </button>
                ))}
              </div>
              <label className="setup-wide">
                {copy("member_notes", language)}
                <textarea
                  onChange={(event) => editMember(index, { description: event.target.value })}
                  rows={2}
                  value={member.description}
                />
              </label>
              <label className="setup-wide">
                {copy("member_must", language)}
                <textarea
                  onChange={(event) =>
                    editMember(index, { must_respect: event.target.value.split("\n") })
                  }
                  rows={2}
                  value={member.must_respect.join("\n")}
                />
              </label>
            </fieldset>
          ))}
        </div>
      ) : null}

      {step === 4 ? (
        <div className="setup-fields">
          <label className="setup-wide">
            {copy("owner_must", language)}
            <textarea
              onChange={(event) => edit({ owner_must_respect: event.target.value })}
              rows={4}
              value={values.owner_must_respect}
            />
          </label>
          {/* Only what the owner confirms here becomes a hard optimizer
              constraint; everything on step 2 stays a preference. */}
          <p className="setup-hint">{copy("preferences", language)}</p>
        </div>
      ) : null}

      {step === 5 ? (
        <dl className="setup-review">
          <dt>{copy("mode", language)}</dt>
          <dd>{trip ? copy(trip.planning_mode, language) : "—"}</dd>
          <dt>{copy("status", language)}</dt>
          <dd>{copy(confirmed ? "confirmed" : "draft", language)}</dd>
          <dt>{copy("main_style", language)}</dt>
          <dd>
            {values.main_style.length
              ? values.main_style.map((code) => copyFrom("TAG_TEXT", code, language)).join(" · ")
              : "—"}
          </dd>
          <dt>{copy("also_enjoy", language)}</dt>
          <dd>{values.also_enjoy.map((code) => copyFrom("TAG_TEXT", code, language)).join(" · ") || "—"}</dd>
          <dt>{copy("avoid", language)}</dt>
          <dd>{values.avoid.map((code) => copyFrom("TAG_TEXT", code, language)).join(" · ") || "—"}</dd>
          <dt>{copy("comfort", language)}</dt>
          <dd>{values.comfort.map((code) => copyFrom("TAG_TEXT", code, language)).join(" · ") || "—"}</dd>
          <dt>{copy("start_date", language)}</dt>
          <dd>{values.start_date || copy("no_dates", language)}</dd>
          <dt>{copy("accommodation", language)}</dt>
          <dd>{copyFrom("ACCOMMODATION_TEXT", values.accommodation_status, language)}</dd>
          <dt>{copy("people", language)}</dt>
          <dd>{1 + values.travellers.length}</dd>
          <dt>{copy("owner_must", language)}</dt>
          <dd>{values.owner_must_respect.trim() || "—"}</dd>
        </dl>
      ) : null}

      <div className="setup-actions">
        {step > 1 ? (
          <button onClick={() => go(step - 1)} type="button">
            {copy("back", language)}
          </button>
        ) : null}
        <button disabled={save.isPending} onClick={() => go(step)} type="button">
          {copy("save_draft", language)}
        </button>
        {step < STEP_COUNT ? (
          <button
            className="setup-primary"
            disabled={save.isPending}
            onClick={() => go(step + 1)}
            type="button"
          >
            {copy("save_continue", language)}
          </button>
        ) : (
          <button
            className="setup-primary"
            disabled={save.isPending}
            onClick={() => go(step, { confirm: true })}
            type="button"
          >
            {copy("confirm", language)}
          </button>
        )}
      </div>
      {/* A disabled primary action always says why, never falls silent. */}
      {step === STEP_COUNT && values.main_style.length === 0 ? (
        <p className="setup-hint">{copy("main_required", language)}</p>
      ) : null}
    </section>
  );
}
