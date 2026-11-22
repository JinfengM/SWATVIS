CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.swat_aoi_vector (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_name text NOT NULL,
    hru_gis text NOT NULL,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    source_file text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS swat_aoi_vector_task_hru_idx
    ON public.swat_aoi_vector (task_name, hru_gis);

CREATE INDEX IF NOT EXISTS swat_aoi_vector_geom_idx
    ON public.swat_aoi_vector USING gist (geom);

CREATE TABLE IF NOT EXISTS public.swat_hru_timeseries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_name text NOT NULL,
    lulc text,
    hru integer,
    gis text NOT NULL,
    sub integer,
    mgt text,
    mon text,
    sim_year integer,
    sim_mon integer,
    sim_day integer,
    sim_time date NOT NULL,
    date_rep date,
    iprint smallint NOT NULL,
    area double precision,
    precip double precision,
    snofall double precision,
    snomelt double precision,
    irr double precision,
    pet double precision,
    et double precision,
    sw_init double precision,
    sw_end double precision,
    perc double precision,
    gw_rchg double precision,
    da_rchg double precision,
    revap double precision,
    sa_irr double precision,
    da_irr double precision,
    sa_st double precision,
    da_st double precision,
    surq_gen double precision,
    surq_cnt double precision,
    tloss double precision,
    latqgen double precision,
    gw_q double precision,
    wyld double precision,
    dailycn double precision,
    tmp_av double precision,
    tmp_mx double precision,
    tmp_mn double precision,
    sol_tmp double precision,
    solar double precision,
    syld double precision,
    usle double precision,
    n_app double precision,
    p_app double precision,
    nauto double precision,
    pauto double precision,
    ngrz double precision,
    pgrz double precision,
    ncfrt double precision,
    pcfrt double precision,
    nrain double precision,
    nfix double precision,
    f_mn double precision,
    a_mn double precision,
    a_sn double precision,
    f_mp double precision,
    ao_lp double precision,
    l_ap double precision,
    a_sp double precision,
    dnit double precision,
    nup double precision,
    pup double precision,
    orgn double precision,
    orgp double precision,
    sedp double precision,
    nsurq double precision,
    nlatq double precision,
    no3l double precision,
    no3gw double precision,
    solp double precision,
    p_gw double precision,
    w_strs double precision,
    tmp_strs double precision,
    n_strs double precision,
    p_strs double precision,
    biom double precision,
    lai double precision,
    yld double precision,
    bactp double precision,
    bactlp double precision,
    wtab_cli double precision,
    wtab_sol double precision,
    sno double precision,
    cmup double precision,
    cmtot double precision,
    qtile double precision,
    tno3 double precision,
    lno3 double precision,
    gw_q_d double precision,
    latqcnt double precision,
    tvap double precision,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS swat_hru_timeseries_task_time_idx
    ON public.swat_hru_timeseries (task_name, iprint, sim_time);

CREATE INDEX IF NOT EXISTS swat_hru_timeseries_join_idx
    ON public.swat_hru_timeseries (task_name, gis, iprint, sim_time);

CREATE OR REPLACE FUNCTION public.swat_fill_hru_time_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.sim_time IS NULL AND NEW.mon IS NOT NULL THEN
        IF NEW.iprint = 2 AND NEW.mon ~ '^\d{4}$' THEN
            NEW.sim_time := to_date(NEW.mon || '-01-01', 'YYYY-MM-DD');
        ELSIF NEW.iprint = 0 AND NEW.mon ~ '^\d{4}-\d{2}$' THEN
            NEW.sim_time := to_date(NEW.mon || '-01', 'YYYY-MM-DD');
        ELSIF NEW.iprint = 1 AND NEW.mon ~ '^\d{4}-\d{2}-\d{2}$' THEN
            NEW.sim_time := to_date(NEW.mon, 'YYYY-MM-DD');
        END IF;
    END IF;

    IF NEW.sim_time IS NOT NULL THEN
        NEW.date_rep := COALESCE(NEW.date_rep, NEW.sim_time);
        NEW.sim_year := COALESCE(NEW.sim_year, EXTRACT(YEAR FROM NEW.sim_time)::integer);
        NEW.sim_mon := COALESCE(NEW.sim_mon, EXTRACT(MONTH FROM NEW.sim_time)::integer);
        NEW.sim_day := COALESCE(NEW.sim_day, EXTRACT(DAY FROM NEW.sim_time)::integer);
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_swat_fill_hru_time_fields ON public.swat_hru_timeseries;

CREATE TRIGGER trg_swat_fill_hru_time_fields
BEFORE INSERT OR UPDATE ON public.swat_hru_timeseries
FOR EACH ROW
EXECUTE FUNCTION public.swat_fill_hru_time_fields();
