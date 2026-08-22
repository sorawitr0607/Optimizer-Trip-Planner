import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type SetupDraft,
  type SetupVocabulary,
  type Trip,
} from "../api/client";
import { copy, copyFormat, copyFrom } from "../i18n/copy";
import { Minus, Plus } from "lucide-react";

import { useLanguage } from "../i18n/LanguageProvider";

// Six, because the wizard now opens on a step that asks for nothing and only says
// what the other five want and why. The step indicator was already
// step-count-agnostic by S3's decision, so this is a constant change, not a
// component change.
const STEP_COUNT = 5;
// The step *indicator* keeps the short nouns, because a progress rail has room for a
// word and not for a sentence. The heading above each step asks the question instead:
// "Trip basics" names a topic and leaves the reader to work out what is wanted, which is
// the whole of why this form read as unfriendly.
const STEP_TITLES = [
  "welcome",
  "trip_basics",
  "owner_style",
  "travellers",
  "review",
];
const STEP_QUESTIONS = [
  "welcome",
  "ask_trip_basics",
  "ask_owner_style",
  "ask_travellers",
  "ask_review",
];
// A POC view convention, not a core rule: setup.py accepts any number.
const MAX_MEMBERS = 8;

function invalidAge(value: number | null): boolean {
  return value !== null && (!Number.isInteger(value) || value < 0 || value > 120);
}

/** Where the trip-style tags live, so a refusal can take the owner to them. */
const MAIN_STYLE_STEP = 3;

/** What the intro step promises, in the order the wizard then asks it. */
const INTRO_STEPS = [
  ["trip_basics", "setup_intro_basics"],
  ["owner_style", "setup_intro_style"],
  ["travellers", "setup_intro_travellers"],
] as const;

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
  active_start: string;
  active_end: string;
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
  active_start: "08:00",
  active_end: "22:00",
  departure_time: null,
  accommodation_status: "not_booked",
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
    active_start: basics.active_start ?? "08:00",
    active_end: basics.active_end ?? "22:00",
    departure_time: basics.departure_time ?? null,
    accommodation_status:
      basics.accommodation_status === "unknown" || !basics.accommodation_status
        ? "not_booked"
        : basics.accommodation_status,
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
  // Null until a step is chosen, so the opening step can depend on the stored
  // draft — which has not loaded yet when this initialises.
  const [chosenStep, setChosenStep] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [flash, setFlash] = useState<{ tone: "ok" | "bad"; code: string } | null>(null);
  const focusTarget = useRef<string | null>(null);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const previousStep = useRef(1);


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

  // Each step starts at the top. The wizard's steps are component state, not routes, so
  // the shell's scroll reset — which keys on `pathname` — cannot see this move at all:
  // pressing "Save & continue" at the foot of a long step left the next one scrolled past
  // its own question, showing whatever happened to sit at that offset.
  //
  // Above the three loading/error returns below, because hooks must run in the same order
  // on every render. Keyed on the **derived** step, not on `chosenStep`: the opening step
  // depends on whether a stored draft exists, so an owner returning to a trip moves 1 → 2
  // when that query lands without `chosenStep` changing at all, and keying on the raw
  // state missed exactly that move. Moving backwards from the step indicator gets the same
  // treatment, which is why this is an effect and not a line in the handler.
  const currentStep = chosenStep ?? (stored.data ? 2 : 1);
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0 });
  }, [currentStep]);
  useEffect(() => {
    const changed = previousStep.current !== currentStep;
    previousStep.current = currentStep;
    if (focusTarget.current) {
      document.getElementById(focusTarget.current)?.focus();
      focusTarget.current = null;
    } else if (changed) {
      stepHeading.current?.focus();
    }
  });

  if (stored.isPending || vocabulary.isPending) return <p>{copy("loading", language)}</p>;
  if (stored.isError) return <p className="field-error">⚠ {stored.error.message}</p>;
  if (vocabulary.isError) return <p className="field-error">⚠ {vocabulary.error.message}</p>;

  const values = draft ?? toDraft(stored.data);
  // Set when a save is refused, cleared the moment a style is picked. Not while typing:
  // the article asks for real-time validation, and the honest reading of that is "say so
  // as soon as it is fixed", not "warn before they have started". Read from `values`
  // rather than `draft`, which is null until the first edit — reading `draft` would have
  // called a stored, perfectly valid setup empty.
  const mainStyleMissing = flash?.code === "main_required" && !values.main_style.length;
  const datesIncomplete =
    values.start_date !== null && (!values.start_date || !values.end_date);
  const datesReversed = Boolean(
    values.start_date && values.end_date && values.end_date < values.start_date,
  );
  const arrivalIncomplete = values.arrival_time === "";
  const departureIncomplete = values.departure_time === "";
  const ownerAgeInvalid = invalidAge(values.owner_age);
  const invalidMemberIndex = values.travellers.findIndex((member) => invalidAge(member.age));
  const confirmed = Boolean(stored.data?.confirmed);
  const trip = trips.data?.find((item) => item.trip_id === tripId);
  const words = vocabulary.data;
  // Step 1 explains the wizard, so it is for a first run. An owner returning to a
  // trip they have already answered for opens on the first question instead — the
  // intro stays reachable by walking back, because the indicator goes backwards.
  const step = currentStep;


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
    const issue = target > step || options.confirm
      ? datesIncomplete
        ? { step: 2, field: values.start_date ? "end-date" : "start-date" }
        : datesReversed
          ? { step: 2, field: "end-date" }
          : arrivalIncomplete
            ? { step: 2, field: "arrival-time" }
            : departureIncomplete
              ? { step: 2, field: "departure-time" }
              : ownerAgeInvalid
                ? { step: 3, field: "owner-age" }
                : invalidMemberIndex >= 0
                  ? { step: 4, field: `member-${invalidMemberIndex}-age` }
                  : null
      : null;
    if (issue) {
      setFlash({ tone: "bad", code: "setup_fix_fields" });
      focusTarget.current = issue.field;
      setChosenStep(issue.step);
      return;
    }
    if (options.confirm && values.main_style.length === 0) {
      setFlash({ tone: "bad", code: "main_required" });
      // **And go to the field.** Confirm lives on the review step and the styles are on
      // step 3, so refusing in place told the owner to fix something that was not on
      // screen — the article's "place the message next to the problematic field", which
      // cannot be satisfied by the message alone when the field is two steps away. The
      // error and the tags are then together, and `MAIN_STYLE_STEP` names the coupling
      // rather than leaving a bare 3 to drift when a step is inserted.
      focusTarget.current = "main-style-first";
      setChosenStep(MAIN_STYLE_STEP);
      return;
    }
    try {
      await save.mutateAsync({ values, confirmed: options.confirm || confirmed });
      if (options.confirm) {
        navigate(`/trips/${tripId}/places`);
        return;
      }
      setFlash({ tone: "ok", code: "step_saved" });
      setChosenStep(Math.min(Math.max(target, 1), STEP_COUNT));
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

      {/* derives-from: element 7 .wizard-progress-4 as .wizard-steps (six steps) */}
      <ol aria-label={copy("setup_progress", language)} className="wizard-steps">
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
                aria-current={number === step ? "step" : undefined}
                disabled={number >= step || save.isPending}
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
        {` · ${copy(STEP_TITLES[step - 1], language)}`}
        {confirmed ? ` · ${copy("confirmed", language)}` : ` · ${copy("draft", language)}`}
      </p>

      <form
        className="setup-step-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void go(step < STEP_COUNT ? step + 1 : step, { confirm: step === STEP_COUNT });
        }}
      >
      {flash ? (
        <p className={flash.tone === "ok" ? "setup-flash" : "field-error"} aria-live="polite">
          {copy(flash.code, language)}
        </p>
      ) : null}

      <h2 className="setup-step-title" ref={stepHeading} tabIndex={-1}>
        {copy(STEP_QUESTIONS[step - 1], language)}
      </h2>

      {/* Nothing is asked here. The wizard used to open on a date checkbox, so a
          first-time owner met a form before ever being told what the form is for
          or how long it runs. */}
      {step === 1 ? (
        <div className="setup-intro">
          <p className="setup-intro-lead">{copy("setup_intro_lead", language)}</p>
          <h2>{copy("setup_intro_what_we_ask", language)}</h2>
          <ol className="setup-intro-list">
            {INTRO_STEPS.map(([title, detail]) => (
              <li key={title}>
                <strong>{copy(title, language)}</strong>
                <p>{copy(detail, language)}</p>
              </li>
            ))}
          </ol>
          <p className="setup-hint">{copy("setup_intro_time", language)}</p>
          <p className="setup-hint">{copy("setup_intro_next", language)}</p>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="setup-fields">
          <p className="setup-hint setup-wide" id="setup-basics-help">
            {copy("setup_basics_help", language)}
          </p>
          <label className="setup-check">
            <input
              aria-controls={values.start_date !== null ? "start-date end-date" : undefined}
              aria-describedby="setup-basics-help"
              checked={values.start_date !== null}
              name="dates-known"
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
                <span>
                  {copy("start_date", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  aria-describedby={datesIncomplete || datesReversed ? "trip-dates-error" : undefined}
                  aria-invalid={datesIncomplete || datesReversed || undefined}
                  autoComplete="off"
                  id="start-date"
                  max={values.end_date || undefined}
                  name="start-date"
                  onChange={(event) => edit({ start_date: event.target.value })}
                  required
                  type="date"
                  value={values.start_date}
                />
              </label>
              <label>
                <span>
                  {copy("end_date", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  aria-describedby={datesIncomplete || datesReversed ? "trip-dates-error" : undefined}
                  aria-invalid={datesIncomplete || datesReversed || undefined}
                  autoComplete="off"
                  id="end-date"
                  min={values.start_date || undefined}
                  name="end-date"
                  onChange={(event) => edit({ end_date: event.target.value })}
                  required
                  type="date"
                  value={values.end_date ?? ""}
                />
              </label>
              {datesIncomplete || datesReversed ? (
                <p className="setup-field-error" id="trip-dates-error" role="alert">
                  ⚠ {copy(datesReversed ? "date_order_invalid" : "date_range_required", language)}
                </p>
              ) : null}
            </>
          )}
          {/* The hours the owner wants to be out, which `_optimizer_input` used to invent
              as 08:00-22:00 for every trip on earth. Two plain time inputs rather than a
              range control: the browser's own picker is the accessible one, and there are
              exactly two values. Pre-filled with the old constants, so leaving them alone
              is the same plan as before. */}
          <fieldset className="setup-hours setup-wide">
            <legend className="setup-legend">{copy("active_hours", language)}</legend>
            <label>
              {copy("active_start", language)}
              <input
                aria-describedby="active-hours-help"
                name="active-start"
                onChange={(event) => edit({ active_start: event.target.value })}
                type="time"
                value={values.active_start}
              />
            </label>
            <label>
              {copy("active_end", language)}
              <input
                aria-describedby="active-hours-help"
                name="active-end"
                onChange={(event) => edit({ active_end: event.target.value })}
                type="time"
                value={values.active_end}
              />
            </label>
            {values.active_start >= values.active_end ? (
              <p className="setup-field-error setup-wide" role="alert">
                ⚠ {copy("date_order_invalid", language)}
              </p>
            ) : null}
          </fieldset>
          <p className="setup-hint setup-wide" id="active-hours-help">
            {copy("active_hours_help", language)}
          </p>

          <label className="setup-check">
            <input
              aria-controls={values.arrival_time !== null ? "arrival-time" : undefined}
              aria-describedby="setup-basics-help"
              checked={values.arrival_time !== null}
              name="arrival-known"
              onChange={(event) =>
                edit({ arrival_time: event.target.checked ? "17:00" : null })
              }
              type="checkbox"
            />
            {copy("arrival_known", language)}
          </label>
          {values.arrival_time === null ? null : (
            <>
              <label>
                <span>
                  {copy("arrival_time", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  aria-describedby={arrivalIncomplete ? "arrival-time-error" : undefined}
                  aria-invalid={arrivalIncomplete || undefined}
                  autoComplete="off"
                  id="arrival-time"
                  name="arrival-time"
                  onChange={(event) => edit({ arrival_time: event.target.value })}
                  required
                  type="time"
                  value={values.arrival_time}
                />
              </label>
              {arrivalIncomplete ? (
                <p className="setup-field-error" id="arrival-time-error" role="alert">
                  ⚠ {copy("time_required", language)}
                </p>
              ) : null}
            </>
          )}
          <label className="setup-check">
            <input
              aria-controls={values.departure_time !== null ? "departure-time" : undefined}
              aria-describedby="setup-basics-help"
              checked={values.departure_time !== null}
              name="departure-known"
              onChange={(event) =>
                edit({ departure_time: event.target.checked ? "11:00" : null })
              }
              type="checkbox"
            />
            {copy("departure_known", language)}
          </label>
          {values.departure_time === null ? null : (
            <>
              <label>
                <span>
                  {copy("departure_time", language)}
                  <span aria-hidden="true" className="setup-required">*</span>
                  <span className="setup-hint"> {copy("required_field", language)}</span>
                </span>
                <input
                  aria-describedby={departureIncomplete ? "departure-time-error" : undefined}
                  aria-invalid={departureIncomplete || undefined}
                  autoComplete="off"
                  id="departure-time"
                  name="departure-time"
                  onChange={(event) => edit({ departure_time: event.target.value })}
                  required
                  type="time"
                  value={values.departure_time}
                />
              </label>
              {departureIncomplete ? (
                <p className="setup-field-error" id="departure-time-error" role="alert">
                  ⚠ {copy("time_required", language)}
                </p>
              ) : null}
            </>
          )}
          <label>
            {copy("accommodation", language)}
            <select
              aria-describedby="accommodation-help"
              name="accommodation-status"
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
          {/* Three one-word options that change what the optimizer anchors every day
              on, with nothing anywhere saying so. The consequence belongs beside the
              control, not in a ticket. */}
          <p className="setup-hint setup-wide" id="accommodation-help">
            {copy(`accommodation_help_${values.accommodation_status}`, language)}
          </p>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="setup-fields">
          <p className="setup-hint setup-wide" id="setup-style-help">
            {copy("setup_style_help", language)}
          </p>
          {/* The error next to the thing that caused it. It was raised only as a flash at
              the head of the form, so on a long step the owner was told "choose a main
              style" with the styles scrolled off screen — the article's point about
              placing the message beside the problem field, and the reason this form could
              refuse without appearing to say why. */}
          {mainStyleMissing ? (
            <p className="setup-field-error" id="main-style-help" role="alert">
              ⚠ {copy("main_required", language)}
            </p>
          ) : (
            <span className="setup-hint setup-wide" id="main-style-help">
              {copy("main_style_help", language)}
            </span>
          )}
          <label>
            {copy("owner_age", language)}
            <input
              aria-describedby={ownerAgeInvalid ? "owner-age-error owner-age-help" : "owner-age-help"}
              aria-invalid={ownerAgeInvalid || undefined}
              autoComplete="off"
              // `numeric`, so a phone offers digits rather than a full keyboard for a
              // field that can only ever hold digits.
              inputMode="numeric"
              id="owner-age"
              max={120}
              min={0}
              name="owner-age"
              onChange={(event) =>
                edit({ owner_age: event.target.value ? Number(event.target.value) : null })
              }
              step={1}
              type="number"
              value={values.owner_age ?? ""}
            />
          </label>
          {ownerAgeInvalid ? (
            <p className="setup-field-error" id="owner-age-error" role="alert">
              ⚠ {copy("age_invalid", language)}
            </p>
          ) : null}
          {/* The hint is *named* and pointed at by the field above, so a screen reader
              reads the guidance with the field instead of stranding it as loose text
              after it. Every hint on this form was unattached; a sighted user could see
              the relationship and nobody else could. */}
          <p className="setup-hint" id="owner-age-help">
            {copy("owner_age_help", language)}
          </p>
          {(["main_style", "also_enjoy", "avoid", "comfort"] as const).map((group) => (
            <fieldset
              aria-describedby={
                group === "main_style" ? "setup-style-help main-style-help" : "setup-style-help"
              }
              aria-invalid={group === "main_style" && mainStyleMissing ? true : undefined}
              className="setup-tags"
              key={group}
            >
              <legend>
                {copy(group, language)}
                {/* Required, marked where the requirement is. The bare " *" said nothing
                    to a screen reader and nothing to anyone who has not learned the
                    convention, so the word is there too. */}
                {group === "main_style" ? (
                  <>
                    <span aria-hidden="true" className="setup-required">*</span>
                    <span className="setup-hint"> {copy("required_field", language)}</span>
                  </>
                ) : null}
              </legend>
              {words.tag_groups[group].map((code) => (
                <button
                  aria-pressed={values[group].includes(code)}
                  className="money-chip"
                  id={group === "main_style" && code === words.tag_groups[group][0]
                    ? "main-style-first"
                    : undefined}
                  key={code}
                  onClick={() => toggle(group, code)}
                  type="button"
                >
                  {copyFrom("TAG_TEXT", code, language)}
                </button>
              ))}
            </fieldset>
          ))}
          {/* Was its own step, which made a wizard of six for one textarea and asked the
              same question twice: `avoid` is soft ("rather not"), this is hard ("cannot").
              Split across two screens the difference was invisible, so it now sits
              directly under the avoid chips where the contrast is the point. */}
          <label className="setup-wide">
            {copy("owner_must", language)}
            <textarea
              aria-describedby="owner-must-help"
              name="owner-requirements"
              onChange={(event) => edit({ owner_must_respect: event.target.value })}
              placeholder={copy("owner_must_placeholder", language)}
              rows={3}
              value={values.owner_must_respect}
            />
          </label>
          <p className="setup-hint setup-wide" id="owner-must-help">
            {copy("owner_must_help", language)}
          </p>
          {/* The free-text boxes never said what happens to what you type, so they
              read as a comment field nobody reads. They are parsed for constraints
              when the plan is built, and an example is worth more than the label. */}
          <label className="setup-wide">
            {copy("description", language)}
            <textarea
              aria-describedby="owner-words-help"
              name="owner-description"
              onChange={(event) => edit({ owner_description: event.target.value })}
              placeholder={copy("owner_description_placeholder", language)}
              rows={3}
              value={values.owner_description}
            />
          </label>
          <p className="setup-hint setup-wide" id="owner-words-help">
            {copy("own_words_help", language)}
          </p>
        </div>
      ) : null}

      {step === 4 ? (
        <div className="setup-fields">
          <p className="setup-hint setup-wide">{copy("setup_travellers_help", language)}</p>
          {/* The same counter the landing page uses for party size, down to the class
              names. It was a `<input type="number">`: two four-pixel browser arrows for
              a value that only ever moves by one, next to a page that already had a
              proper control for exactly this question. `MAX_MEMBERS` still bounds it,
              and the value stays readable as text rather than living inside a spinner. */}
          <div className="setup-counter-group">
            <span className="setup-counter-label" id="member-count-label">
              {copy("member_count", language)}
            </span>
            <div
              aria-describedby="member-count-help"
              aria-labelledby="member-count-label"
              className="setup-counter"
              role="group"
            >
              <button
                aria-label={copy("landing_lab_decrease", language)}
                className="setup-counter-btn"
                disabled={values.travellers.length <= 0}
                onClick={() => setMemberCount(Math.max(0, values.travellers.length - 1))}
                type="button"
              >
                <Minus aria-hidden="true" size={13} />
              </button>
              {/* Announced on change, because the number is the only thing that moves
                  and a screen reader would otherwise hear nothing at all. */}
              <span aria-live="polite" className="setup-counter-val">
                {values.travellers.length} {copy("travellers", language)}
              </span>
              <button
                aria-label={copy("landing_lab_increase", language)}
                className="setup-counter-btn"
                disabled={values.travellers.length >= MAX_MEMBERS}
                onClick={() =>
                  setMemberCount(Math.min(MAX_MEMBERS, values.travellers.length + 1))
                }
                type="button"
              >
                <Plus aria-hidden="true" size={13} />
              </button>
            </div>
          </div>
          <p className="setup-hint" id="member-count-help">
            {copy("member_count_help", language)}
          </p>
          {values.travellers.map((member, index) => (
            <fieldset className="setup-member setup-wide" key={member.traveller_id}>
              <legend>{member.traveller_id}</legend>
              <label>
                {copy("member_name", language)}
                <input
                  autoCapitalize="words"
                  autoComplete="off"
                  autoCorrect="off"
                  name={`member-${index}-name`}
                  onChange={(event) => editMember(index, { label: event.target.value })}
                  spellCheck={false}
                  type="text"
                  value={member.label}
                />
              </label>
              <label>
                {copy("member_age", language)}
                <input
                  aria-describedby={
                    invalidMemberIndex === index ? `member-${index}-age-error` : undefined
                  }
                  aria-invalid={invalidMemberIndex === index || undefined}
                  autoComplete="off"
                  id={`member-${index}-age`}
                  inputMode="numeric"
                  max={120}
                  min={0}
                  name={`member-${index}-age`}
                  onChange={(event) =>
                    editMember(index, {
                      age: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  step={1}
                  type="number"
                  value={member.age ?? ""}
                />
                {invalidMemberIndex === index ? (
                  <span className="setup-field-error" id={`member-${index}-age-error`} role="alert">
                    ⚠ {copy("age_invalid", language)}
                  </span>
                ) : null}
              </label>
              <fieldset
                aria-describedby={`member-${index}-tags-help`}
                className="setup-tags setup-wide"
              >
                <legend className="setup-legend">{copy("member_tags", language)}</legend>
                <p className="setup-hint setup-wide" id={`member-${index}-tags-help`}>
                  {copy("member_tags_help", language)}
                </p>
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
              </fieldset>
              <label className="setup-wide">
                {copy("member_notes", language)}
                <textarea
                  name={`member-${index}-notes`}
                  onChange={(event) => editMember(index, { description: event.target.value })}
                  placeholder={copy("member_notes_placeholder", language)}
                  rows={2}
                  value={member.description}
                />
              </label>
              <label className="setup-wide">
                {copy("member_must", language)}
                <textarea
                  name={`member-${index}-requirements`}
                  onChange={(event) =>
                    editMember(index, { must_respect: event.target.value.split("\n") })
                  }
                  placeholder={copy("member_must_placeholder", language)}
                  rows={2}
                  value={member.must_respect.join("\n")}
                />
              </label>
            </fieldset>
          ))}
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
          <button disabled={save.isPending} onClick={() => go(step - 1)} type="button">
            {copy("back", language)}
          </button>
        ) : null}
        {/* Step 1 asks for nothing, so there is nothing to save a draft of. */}
        {step > 1 ? (
          <button disabled={save.isPending} onClick={() => go(step)} type="button">
            {copy("save_draft", language)}
          </button>
        ) : null}
        {step < STEP_COUNT ? (
          <button
            className="setup-primary"
            disabled={save.isPending}
            type="submit"
          >
            {copy(step === 1 ? "continue_trip" : "save_continue", language)}
          </button>
        ) : (
          <button
            className="setup-primary"
            disabled={save.isPending}
            type="submit"
          >
            {copy("confirm", language)}
          </button>
        )}
      </div>
      {save.isPending ? (
        <p aria-live="polite" aria-busy="true" className="thinking">
          <span className="thinking-dot" />
          <span>{copy("saving_step", language)}</span>
        </p>
      ) : null}
      {/* A disabled primary action always says why, never falls silent. */}
      {step === STEP_COUNT && values.main_style.length === 0 ? (
        <p className="setup-hint">{copy("main_required", language)}</p>
      ) : null}
      </form>
    </section>
  );
}
