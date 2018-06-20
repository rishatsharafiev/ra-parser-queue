--
-- PostgreSQL database dump
--

-- Dumped from database version 9.6.9
-- Dumped by pg_dump version 10.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: proxy; Type: TABLE; Schema: public; Owner: ra
--

CREATE TABLE public.proxy (
    id integer NOT NULL,
    url character varying(2044) NOT NULL,
    schema character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    ping integer,
    is_frozen boolean DEFAULT false NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    source character varying(1000) DEFAULT ''::character varying NOT NULL
);


ALTER TABLE public.proxy OWNER TO ra;

--
-- Name: proxy_id_seq; Type: SEQUENCE; Schema: public; Owner: ra
--

CREATE SEQUENCE public.proxy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.proxy_id_seq OWNER TO ra;

--
-- Name: proxy_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ra
--

ALTER SEQUENCE public.proxy_id_seq OWNED BY public.proxy.id;


--
-- Name: proxy id; Type: DEFAULT; Schema: public; Owner: ra
--

ALTER TABLE ONLY public.proxy ALTER COLUMN id SET DEFAULT nextval('public.proxy_id_seq'::regclass);


--
-- Name: proxy proxy_pkey; Type: CONSTRAINT; Schema: public; Owner: ra
--

ALTER TABLE ONLY public.proxy
    ADD CONSTRAINT proxy_pkey PRIMARY KEY (id);


--
-- Name: proxy unique_url_schema; Type: CONSTRAINT; Schema: public; Owner: ra
--

ALTER TABLE ONLY public.proxy
    ADD CONSTRAINT unique_url_schema UNIQUE (url, schema);


--
-- PostgreSQL database dump complete
--

