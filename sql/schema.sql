--
-- PostgreSQL database dump
--

\restrict 9uRtoeQO1MJlvpIia0KidmqHhwm7NjwQ4cMgMbn1Xrrysg48BYAcZnGOFIZFzBZ

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

-- Started on 2026-11-20 23:18:58

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 223 (class 1259 OID 24695)
-- Name: audio_features; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audio_features (
    audio_id bigint NOT NULL,
    feature_vector double precision[] NOT NULL,
    CONSTRAINT check_60_dimensions CHECK (((array_ndims(feature_vector) = 1) AND (cardinality(feature_vector) = 60)))
);


ALTER TABLE public.audio_features OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 24676)
-- Name: audio_files; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audio_files (
    audio_id bigint NOT NULL,
    instrument_id smallint NOT NULL,
    filename text NOT NULL,
    file_path text NOT NULL
);


ALTER TABLE public.audio_files OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 24675)
-- Name: audio_files_audio_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.audio_files_audio_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audio_files_audio_id_seq OWNER TO postgres;

--
-- TOC entry 5033 (class 0 OID 0)
-- Dependencies: 221
-- Name: audio_files_audio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.audio_files_audio_id_seq OWNED BY public.audio_files.audio_id;


--
-- TOC entry 220 (class 1259 OID 24665)
-- Name: instruments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.instruments (
    instrument_id smallint NOT NULL,
    instrument_name character varying(100) NOT NULL
);


ALTER TABLE public.instruments OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 24664)
-- Name: instruments_instrument_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.instruments_instrument_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.instruments_instrument_id_seq OWNER TO postgres;

--
-- TOC entry 5034 (class 0 OID 0)
-- Dependencies: 219
-- Name: instruments_instrument_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.instruments_instrument_id_seq OWNED BY public.instruments.instrument_id;


--
-- TOC entry 4866 (class 2604 OID 24679)
-- Name: audio_files audio_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_files ALTER COLUMN audio_id SET DEFAULT nextval('public.audio_files_audio_id_seq'::regclass);


--
-- TOC entry 4865 (class 2604 OID 24668)
-- Name: instruments instrument_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instruments ALTER COLUMN instrument_id SET DEFAULT nextval('public.instruments_instrument_id_seq'::regclass);


--
-- TOC entry 4878 (class 2606 OID 24704)
-- Name: audio_features audio_features_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_features
    ADD CONSTRAINT audio_features_pkey PRIMARY KEY (audio_id);


--
-- TOC entry 4873 (class 2606 OID 24689)
-- Name: audio_files audio_files_file_path_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_files
    ADD CONSTRAINT audio_files_file_path_key UNIQUE (file_path);


--
-- TOC entry 4875 (class 2606 OID 24687)
-- Name: audio_files audio_files_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_files
    ADD CONSTRAINT audio_files_pkey PRIMARY KEY (audio_id);


--
-- TOC entry 4869 (class 2606 OID 24674)
-- Name: instruments instruments_instrument_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instruments
    ADD CONSTRAINT instruments_instrument_name_key UNIQUE (instrument_name);


--
-- TOC entry 4871 (class 2606 OID 24672)
-- Name: instruments instruments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.instruments
    ADD CONSTRAINT instruments_pkey PRIMARY KEY (instrument_id);


--
-- TOC entry 4876 (class 1259 OID 24710)
-- Name: idx_audio_instrument; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audio_instrument ON public.audio_files USING btree (instrument_id);


--
-- TOC entry 4880 (class 2606 OID 24705)
-- Name: audio_features audio_features_audio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_features
    ADD CONSTRAINT audio_features_audio_id_fkey FOREIGN KEY (audio_id) REFERENCES public.audio_files(audio_id) ON DELETE CASCADE;


--
-- TOC entry 4879 (class 2606 OID 24690)
-- Name: audio_files audio_files_instrument_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audio_files
    ADD CONSTRAINT audio_files_instrument_id_fkey FOREIGN KEY (instrument_id) REFERENCES public.instruments(instrument_id);


-- Completed on 2026-11-20 23:18:58

--
-- PostgreSQL database dump complete
--

\unrestrict 9uRtoeQO1MJlvpIia0KidmqHhwm7NjwQ4cMgMbn1Xrrysg48BYAcZnGOFIZFzBZ

