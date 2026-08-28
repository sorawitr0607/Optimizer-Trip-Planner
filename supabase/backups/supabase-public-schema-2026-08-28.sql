-- Optimizer Trip Planner live Supabase structure backup.
-- Captured: 2026-08-28T03:57:34.736898+00:00
-- Scope: public schema only; no rows, owners, grants, or credentials.
-- Restore into an empty PostgreSQL database with psql --set ON_ERROR_STOP=1 --file FILE.

--
-- PostgreSQL database dump
--

\restrict HDmT2nBd6M11rtTauBH62KLVrTq5dz8zLUYPPujqMvSXACaI6Yknu9Y0fqC2spc

-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: refuse_write(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refuse_write() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION '%', TG_ARGV[0];
END;
$$;


--
-- Name: refuse_write_unless_trip_deleting(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.refuse_write_unless_trip_deleting() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM trip_deletions WHERE trip_id = OLD.trip_id) THEN
        RAISE EXCEPTION '%', TG_ARGV[0];
    END IF;
    RETURN OLD;
END;
$$;


SET default_table_access_method = heap;

--
-- Name: active_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.active_plans (
    trip_id text NOT NULL,
    plan_version_id text NOT NULL
);


--
-- Name: candidate_choices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candidate_choices (
    trip_id text NOT NULL,
    place_id text NOT NULL,
    discovery_run_id text NOT NULL,
    action text NOT NULL,
    reason text,
    candidate_json text NOT NULL,
    candidate_sha256 text NOT NULL,
    updated_at text NOT NULL,
    CONSTRAINT candidate_choices_action_check CHECK ((action = ANY (ARRAY['must_do'::text, 'interested'::text, 'maybe'::text, 'not_for_trip'::text])))
);


--
-- Name: checklist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checklist_items (
    id text NOT NULL,
    trip_id text NOT NULL,
    generated_key text,
    origin text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    dismissed bigint NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    CONSTRAINT checklist_items_dismissed_check CHECK ((dismissed = ANY (ARRAY[(0)::bigint, (1)::bigint]))),
    CONSTRAINT checklist_items_origin_check CHECK ((origin = ANY (ARRAY['generated'::text, 'manual'::text])))
);


--
-- Name: comfort_acceptances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comfort_acceptances (
    trip_id text NOT NULL,
    code text NOT NULL,
    accepted_value double precision NOT NULL,
    threshold_value double precision NOT NULL,
    updated_at text NOT NULL
);


--
-- Name: cost_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_items (
    id text NOT NULL,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL
);


--
-- Name: discovery_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discovery_runs (
    id text NOT NULL,
    trip_id text NOT NULL,
    setup_sha256 text NOT NULL,
    provider text NOT NULL,
    status text NOT NULL,
    candidates_json text NOT NULL,
    candidates_sha256 text NOT NULL,
    report_json text NOT NULL,
    report_sha256 text NOT NULL,
    created_at text NOT NULL,
    CONSTRAINT discovery_runs_status_check CHECK ((status = ANY (ARRAY['verified'::text, 'stale'::text, 'unavailable'::text, 'error'::text])))
);


--
-- Name: exchange_rate_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exchange_rate_snapshots (
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    updated_at text NOT NULL
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id text NOT NULL,
    kind text NOT NULL,
    trip_id text NOT NULL,
    payload_json text NOT NULL,
    status text NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    claimed_by text,
    claimed_at text,
    created_at text NOT NULL,
    finished_at text,
    result_json text,
    error text,
    progress integer
);


--
-- Name: optimization_previews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.optimization_previews (
    trip_id text NOT NULL,
    input_json text NOT NULL,
    input_sha256 text NOT NULL,
    proposal_json text NOT NULL,
    proposal_sha256 text NOT NULL,
    created_at text NOT NULL
);


--
-- Name: paid_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paid_usage (
    id text NOT NULL,
    trip_id text,
    operation text NOT NULL,
    provider text NOT NULL,
    request_count bigint NOT NULL,
    estimated_usd double precision NOT NULL,
    outcome text NOT NULL,
    detail_json text NOT NULL,
    created_at text NOT NULL,
    CONSTRAINT paid_usage_outcome_check CHECK ((outcome = ANY (ARRAY['success'::text, 'error'::text, 'cached'::text])))
);


--
-- Name: paid_usage_cap; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paid_usage_cap (
    id bigint NOT NULL,
    cap_usd double precision NOT NULL,
    updated_at text NOT NULL,
    CONSTRAINT paid_usage_cap_id_check CHECK ((id = 1))
);


--
-- Name: place_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.place_evidence (
    trip_id text NOT NULL,
    place_id text NOT NULL,
    kind text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL
);


--
-- Name: plan_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plan_revisions (
    id text NOT NULL,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL
);


--
-- Name: plan_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plan_versions (
    id text NOT NULL,
    trip_id text NOT NULL,
    parent_version_id text,
    cause text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL
);


--
-- Name: provider_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provider_cache (
    provider text NOT NULL,
    request_fingerprint text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL
);


--
-- Name: revision_drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revision_drafts (
    trip_id text NOT NULL,
    base_version_id text,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL
);


--
-- Name: route_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.route_snapshots (
    id text NOT NULL,
    trip_id text NOT NULL,
    origin_id text NOT NULL,
    destination_id text NOT NULL,
    mode text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL
);


--
-- Name: schema_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_meta (
    key text NOT NULL,
    value text NOT NULL
);


--
-- Name: split_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.split_rows (
    id text NOT NULL,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL
);


--
-- Name: split_settled_markers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.split_settled_markers (
    trip_id text NOT NULL,
    traveller_id text NOT NULL,
    settled_net_thb double precision NOT NULL,
    updated_at text NOT NULL
);


--
-- Name: trip_deletions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trip_deletions (
    trip_id text NOT NULL
);


--
-- Name: trip_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trip_evidence (
    trip_id text NOT NULL,
    kind text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL
);


--
-- Name: trip_setups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trip_setups (
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    confirmed bigint NOT NULL,
    updated_at text NOT NULL,
    CONSTRAINT trip_setups_confirmed_check CHECK ((confirmed = ANY (ARRAY[(0)::bigint, (1)::bigint])))
);


--
-- Name: trips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trips (
    id text NOT NULL,
    name text NOT NULL,
    destination text NOT NULL,
    planning_mode text NOT NULL,
    language text NOT NULL,
    created_at text NOT NULL,
    owner_token text,
    CONSTRAINT trips_language_check CHECK ((language = ANY (ARRAY['en'::text, 'th'::text]))),
    CONSTRAINT trips_planning_mode_check CHECK ((planning_mode = ANY (ARRAY['explore_first'::text, 'ready_to_schedule'::text])))
);


--
-- Name: active_plans active_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_plans
    ADD CONSTRAINT active_plans_pkey PRIMARY KEY (trip_id);


--
-- Name: active_plans active_plans_plan_version_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_plans
    ADD CONSTRAINT active_plans_plan_version_id_key UNIQUE (plan_version_id);


--
-- Name: candidate_choices candidate_choices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_choices
    ADD CONSTRAINT candidate_choices_pkey PRIMARY KEY (trip_id, place_id);


--
-- Name: checklist_items checklist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_pkey PRIMARY KEY (id);


--
-- Name: checklist_items checklist_items_trip_id_generated_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_trip_id_generated_key_key UNIQUE (trip_id, generated_key);


--
-- Name: comfort_acceptances comfort_acceptances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comfort_acceptances
    ADD CONSTRAINT comfort_acceptances_pkey PRIMARY KEY (trip_id, code);


--
-- Name: cost_items cost_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_items
    ADD CONSTRAINT cost_items_pkey PRIMARY KEY (id);


--
-- Name: discovery_runs discovery_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discovery_runs
    ADD CONSTRAINT discovery_runs_pkey PRIMARY KEY (id);


--
-- Name: exchange_rate_snapshots exchange_rate_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rate_snapshots
    ADD CONSTRAINT exchange_rate_snapshots_pkey PRIMARY KEY (trip_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: optimization_previews optimization_previews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_previews
    ADD CONSTRAINT optimization_previews_pkey PRIMARY KEY (trip_id);


--
-- Name: paid_usage_cap paid_usage_cap_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paid_usage_cap
    ADD CONSTRAINT paid_usage_cap_pkey PRIMARY KEY (id);


--
-- Name: paid_usage paid_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paid_usage
    ADD CONSTRAINT paid_usage_pkey PRIMARY KEY (id);


--
-- Name: place_evidence place_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_evidence
    ADD CONSTRAINT place_evidence_pkey PRIMARY KEY (trip_id, place_id, kind);


--
-- Name: plan_revisions plan_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_revisions
    ADD CONSTRAINT plan_revisions_pkey PRIMARY KEY (id);


--
-- Name: plan_versions plan_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_pkey PRIMARY KEY (id);


--
-- Name: plan_versions plan_versions_trip_id_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_trip_id_id_key UNIQUE (trip_id, id);


--
-- Name: provider_cache provider_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provider_cache
    ADD CONSTRAINT provider_cache_pkey PRIMARY KEY (provider, request_fingerprint);


--
-- Name: revision_drafts revision_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_drafts
    ADD CONSTRAINT revision_drafts_pkey PRIMARY KEY (trip_id);


--
-- Name: route_snapshots route_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.route_snapshots
    ADD CONSTRAINT route_snapshots_pkey PRIMARY KEY (id);


--
-- Name: route_snapshots route_snapshots_trip_id_origin_id_destination_id_mode_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.route_snapshots
    ADD CONSTRAINT route_snapshots_trip_id_origin_id_destination_id_mode_key UNIQUE (trip_id, origin_id, destination_id, mode);


--
-- Name: schema_meta schema_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_meta
    ADD CONSTRAINT schema_meta_pkey PRIMARY KEY (key);


--
-- Name: split_rows split_rows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.split_rows
    ADD CONSTRAINT split_rows_pkey PRIMARY KEY (id);


--
-- Name: split_settled_markers split_settled_markers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.split_settled_markers
    ADD CONSTRAINT split_settled_markers_pkey PRIMARY KEY (trip_id, traveller_id);


--
-- Name: trip_deletions trip_deletions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_deletions
    ADD CONSTRAINT trip_deletions_pkey PRIMARY KEY (trip_id);


--
-- Name: trip_evidence trip_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_evidence
    ADD CONSTRAINT trip_evidence_pkey PRIMARY KEY (trip_id, kind);


--
-- Name: trip_setups trip_setups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_setups
    ADD CONSTRAINT trip_setups_pkey PRIMARY KEY (trip_id);


--
-- Name: trips trips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trips
    ADD CONSTRAINT trips_pkey PRIMARY KEY (id);


--
-- Name: jobs_by_trip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_by_trip ON public.jobs USING btree (trip_id, created_at);


--
-- Name: jobs_claimable; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_claimable ON public.jobs USING btree (status, created_at);


--
-- Name: trips_owner_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX trips_owner_token ON public.trips USING btree (owner_token);


--
-- Name: discovery_runs discovery_runs_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER discovery_runs_no_delete BEFORE DELETE ON public.discovery_runs FOR EACH ROW EXECUTE FUNCTION public.refuse_write_unless_trip_deleting('discovery runs are immutable');


--
-- Name: discovery_runs discovery_runs_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER discovery_runs_no_update BEFORE UPDATE ON public.discovery_runs FOR EACH ROW EXECUTE FUNCTION public.refuse_write('discovery runs are immutable');


--
-- Name: paid_usage paid_usage_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER paid_usage_no_delete BEFORE DELETE ON public.paid_usage FOR EACH ROW EXECUTE FUNCTION public.refuse_write('paid usage entries are immutable');


--
-- Name: paid_usage paid_usage_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER paid_usage_no_update BEFORE UPDATE ON public.paid_usage FOR EACH ROW EXECUTE FUNCTION public.refuse_write('paid usage entries are immutable');


--
-- Name: plan_revisions plan_revisions_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER plan_revisions_no_delete BEFORE DELETE ON public.plan_revisions FOR EACH ROW EXECUTE FUNCTION public.refuse_write_unless_trip_deleting('revision history is immutable');


--
-- Name: plan_revisions plan_revisions_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER plan_revisions_no_update BEFORE UPDATE ON public.plan_revisions FOR EACH ROW EXECUTE FUNCTION public.refuse_write('revision history is immutable');


--
-- Name: plan_versions plan_versions_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER plan_versions_no_delete BEFORE DELETE ON public.plan_versions FOR EACH ROW EXECUTE FUNCTION public.refuse_write_unless_trip_deleting('plan versions are immutable');


--
-- Name: plan_versions plan_versions_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER plan_versions_no_update BEFORE UPDATE ON public.plan_versions FOR EACH ROW EXECUTE FUNCTION public.refuse_write('plan versions are immutable');


--
-- Name: active_plans active_plans_trip_id_plan_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_plans
    ADD CONSTRAINT active_plans_trip_id_plan_version_id_fkey FOREIGN KEY (trip_id, plan_version_id) REFERENCES public.plan_versions(trip_id, id);


--
-- Name: candidate_choices candidate_choices_discovery_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_choices
    ADD CONSTRAINT candidate_choices_discovery_run_id_fkey FOREIGN KEY (discovery_run_id) REFERENCES public.discovery_runs(id);


--
-- Name: candidate_choices candidate_choices_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_choices
    ADD CONSTRAINT candidate_choices_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: checklist_items checklist_items_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: comfort_acceptances comfort_acceptances_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comfort_acceptances
    ADD CONSTRAINT comfort_acceptances_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: cost_items cost_items_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_items
    ADD CONSTRAINT cost_items_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: discovery_runs discovery_runs_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discovery_runs
    ADD CONSTRAINT discovery_runs_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: exchange_rate_snapshots exchange_rate_snapshots_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rate_snapshots
    ADD CONSTRAINT exchange_rate_snapshots_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: optimization_previews optimization_previews_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_previews
    ADD CONSTRAINT optimization_previews_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: place_evidence place_evidence_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.place_evidence
    ADD CONSTRAINT place_evidence_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: plan_revisions plan_revisions_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_revisions
    ADD CONSTRAINT plan_revisions_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: plan_versions plan_versions_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: plan_versions plan_versions_trip_id_parent_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_trip_id_parent_version_id_fkey FOREIGN KEY (trip_id, parent_version_id) REFERENCES public.plan_versions(trip_id, id);


--
-- Name: revision_drafts revision_drafts_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_drafts
    ADD CONSTRAINT revision_drafts_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: route_snapshots route_snapshots_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.route_snapshots
    ADD CONSTRAINT route_snapshots_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: split_rows split_rows_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.split_rows
    ADD CONSTRAINT split_rows_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: split_settled_markers split_settled_markers_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.split_settled_markers
    ADD CONSTRAINT split_settled_markers_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: trip_evidence trip_evidence_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_evidence
    ADD CONSTRAINT trip_evidence_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- Name: trip_setups trip_setups_trip_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trip_setups
    ADD CONSTRAINT trip_setups_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES public.trips(id);


--
-- PostgreSQL database dump complete
--

\unrestrict HDmT2nBd6M11rtTauBH62KLVrTq5dz8zLUYPPujqMvSXACaI6Yknu9Y0fqC2spc

