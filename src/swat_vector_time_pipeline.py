"""One-command SWAT vector time rendering pipeline.

This script implements the recommended publication workflow:
1. initialize a compact PostGIS schema;
2. import the SWAT HRU polygon layer;
3. import SWAT output.hru time series;
4. publish parameterized GeoServer SQL Views for vector time rendering;
5. optionally write result_display/geoserver_config.js for the included viewer.

The pipeline intentionally avoids the project-specific MySQL handoff used by the
legacy scripts. PostgreSQL/PostGIS and GeoServer are the only required services.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import geopandas as gpd
import numpy as np
import pandas as pd
import psycopg2
import requests
import yaml
from psycopg2.extras import Json, execute_values
from requests.auth import HTTPBasicAuth

LOG = logging.getLogger("swat-vector-time")

DEFAULT_CONFIG = "swat_vector_time_config.yaml"
DEFAULT_SCHEMA_SQL = Path("sql") / "postgresql" / "swat_vector_time_schema.sql"
DEFAULT_SRID = 4326
VALID_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VALID_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")

HRU_MANUAL_FIELDS = [
    ("lulc", "a4"), ("hru", "i4"), ("gis", "i8"), ("sub", "i4"), ("mgt", "i4"),
    ("mon", "i4"), ("area", "f10.3"), ("precip", "f10.3"), ("snofall", "f10.3"),
    ("snomelt", "f10.3"), ("irr", "f10.3"), ("pet", "f10.3"), ("et", "f10.3"),
    ("sw_init", "f10.3"), ("sw_end", "f10.3"), ("perc", "f10.3"), ("gw_rchg", "f10.3"),
    ("da_rchg", "f10.3"), ("revap", "f10.3"), ("sa_irr", "f10.3"), ("da_irr", "f10.3"),
    ("sa_st", "f10.3"), ("da_st", "f10.3"), ("surq_gen", "f10.3"), ("surq_cnt", "f10.3"),
    ("tloss", "f10.3"), ("latqgen", "f10.3"), ("gw_q", "f10.3"), ("wyld", "f10.3"),
    ("dailycn", "f10.3"), ("tmp_av", "f10.3"), ("tmp_mx", "f10.3"), ("tmp_mn", "f10.3"),
    ("sol_tmp", "f10.3"), ("solar", "f10.3"), ("syld", "f10.3"), ("usle", "f10.3"),
    ("n_app", "f10.3"), ("p_app", "f10.3"), ("nauto", "f10.3"), ("pauto", "f10.3"),
    ("ngrz", "f10.3"), ("pgrz", "f10.3"), ("ncfrt", "f10.3"), ("pcfrt", "f10.3"),
    ("nrain", "f10.3"), ("nfix", "f10.3"), ("f_mn", "f10.3"), ("a_mn", "f10.3"),
    ("a_sn", "f10.3"), ("f_mp", "f10.3"), ("ao_lp", "f10.3"), ("l_ap", "f10.3"),
    ("a_sp", "f10.3"), ("dnit", "f10.3"), ("nup", "f10.3"), ("pup", "f10.3"),
    ("orgn", "f10.3"), ("orgp", "f10.3"), ("sedp", "f10.3"), ("nsurq", "f10.3"),
    ("nlatq", "f10.3"), ("no3l", "f10.3"), ("no3gw", "f10.3"), ("solp", "f10.3"),
    ("p_gw", "f10.3"), ("w_strs", "f10.3"), ("tmp_strs", "f10.3"), ("n_strs", "f10.3"),
    ("p_strs", "f10.3"), ("biom", "f10.3"), ("lai", "f10.3"), ("yld", "f10.3"),
    ("bactp", "f10.3"), ("bactlp", "f10.3"), ("wtab_cli", "f10.3"), ("wtab_sol", "f10.3"),
    ("sno", "f10.3"), ("cmup", "f10.3"), ("cmtot", "f10.3"), ("qtile", "f10.3"),
    ("tno3", "f10.3"), ("lno3", "f10.3"), ("gw_q_d", "f10.3"), ("latqcnt", "f10.3"),
]

HRU_OUTPUT_FIELDS = [name for name, _ in HRU_MANUAL_FIELDS]

HRU_MANUAL_COLSPECS = [
    (0, 4), (6, 9), (10, 19), (22, 24), (28, 29), (30, 34), (34, 44),
    (47, 54), (58, 64), (68, 74), (78, 84), (86, 94), (96, 104), (108, 114),
    (118, 124), (128, 134), (138, 144), (148, 154), (157, 164), (168, 174),
    (178, 184), (187, 194), (196, 204), (208, 214), (218, 224), (228, 234),
    (238, 244), (248, 254), (258, 264), (267, 274), (278, 284), (288, 294),
    (297, 304), (307, 314), (317, 324), (328, 334), (338, 344), (348, 354),
    (358, 364), (368, 374), (378, 384), (388, 394), (398, 404), (408, 414),
    (418, 424), (428, 434), (438, 444), (447, 454), (458, 464), (468, 474),
    (477, 484), (488, 494), (497, 504), (507, 514), (518, 524), (527, 534),
    (537, 544), (548, 554), (558, 564), (568, 574), (578, 584), (588, 594),
    (598, 604), (608, 614), (618, 624), (628, 634), (637, 644), (647, 654),
    (658, 664), (668, 674), (678, 684), (688, 694), (698, 704), (705, 715),
    (716, 726), (727, 736), (737, 746), (747, 756), (757, 766), (767, 776),
    (777, 786), (787, 796), (797, 806), (811, 816), (820, 826),
]

INTEGER_COLUMNS = {"hru", "sub", "sim_year", "sim_mon", "sim_day", "iprint"}
STRING_COLUMNS = {"lulc", "gis", "mgt", "mon", "task_name"}
TIME_SCALE_BY_IPRINT = {0: "monthly", 1: "daily", 2: "yearly"}
IPRINT_BY_TIME_SCALE = {v: k for k, v in TIME_SCALE_BY_IPRINT.items()}


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def configure_logging(cfg: dict[str, Any]) -> None:
    level_name = str(cfg.get("logging", {}).get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    LOG.setLevel(level)


def require_table_name(value: str, key: str) -> str:
    if not isinstance(value, str) or not VALID_TABLE_RE.match(value):
        raise ValueError(f"Invalid {key}: {value!r}")
    return value


def require_column_name(value: str, key: str) -> str:
    if not isinstance(value, str) or not VALID_NAME_RE.match(value):
        raise ValueError(f"Invalid {key}: {value!r}")
    return value


def qname(table: str) -> str:
    require_table_name(table, "table")
    return ".".join(f'"{part}"' for part in table.split("."))


def slug(value: str, repl: str = "-") -> str:
    value = value.strip().replace(" ", repl).replace(".", repl)
    value = SLUG_RE.sub(repl, value)
    value = re.sub(rf"{re.escape(repl)}+", repl, value).strip(repl)
    return (value or "layer")[:128]


def pg_connect(db_cfg: dict[str, Any]):
    return psycopg2.connect(
        host=db_cfg.get("host", "localhost"),
        port=int(db_cfg.get("port", 5432)),
        user=db_cfg.get("user", "postgres"),
        password=db_cfg.get("password", ""),
        dbname=db_cfg.get("database", "postgres"),
        sslmode=db_cfg.get("sslmode", "prefer"),
    )


def init_schema(db_cfg: dict[str, Any], sql_path: str | Path) -> None:
    sql_file = Path(sql_path)
    if not sql_file.exists():
        raise FileNotFoundError(f"Schema SQL not found: {sql_file}")
    LOG.info("Initializing PostGIS schema from %s", sql_file)
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute(sql_file.read_text(encoding="utf-8"))


def read_iprint(file_cio: str | Path) -> int:
    lines = Path(file_cio).read_text(encoding="utf-8", errors="ignore").splitlines()
    if len(lines) < 59:
        raise ValueError("file.cio has fewer than 59 lines")
    value = int(lines[58].split("|")[0].strip())
    if value not in TIME_SCALE_BY_IPRINT:
        raise ValueError(f"Unsupported IPRINT value in file.cio: {value}")
    return value


def read_simulation_start(file_cio: str | Path) -> int:
    lines = Path(file_cio).read_text(encoding="utf-8", errors="ignore").splitlines()
    if len(lines) < 9:
        raise ValueError("file.cio has too few lines to read IYR")
    for line in lines[7:11]:
        if "IYR" in line:
            return int(line.split("|")[0].split(":")[0].strip())
    return int(lines[7].split("|")[0].split(":")[0].strip())


def read_hru_strict_frame(hru_file: str | Path) -> pd.DataFrame:
    if len(HRU_MANUAL_COLSPECS) != len(HRU_OUTPUT_FIELDS):
        raise ValueError("HRU fixed-width colspec count does not match field count")

    df = pd.read_fwf(
        hru_file,
        colspecs=HRU_MANUAL_COLSPECS,
        names=HRU_OUTPUT_FIELDS,
        skiprows=9,
        dtype="str",
    )
    if df.empty:
        raise ValueError("output.hru is empty")

    df = df.dropna(how="all").copy()
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].str.strip()

    missing_hru = df["hru"].isna() | (df["hru"].astype(str).str.strip() == "")
    if missing_hru.any():
        LOG.warning("Dropping %s HRU rows with missing hru code", int(missing_hru.sum()))
        df = df.loc[~missing_hru].copy()

    return df[HRU_OUTPUT_FIELDS]


def cast_hru_frame(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if col in INTEGER_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif col in STRING_COLUMNS:
            df[col] = df[col].astype(str)
        elif col != "sim_time":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_time_columns(df: pd.DataFrame, iprint: int, file_cio: str | Path) -> pd.DataFrame:
    df = df.copy()
    df["iprint"] = iprint

    if iprint == 0:
        hru_count = df["hru"].drop_duplicates().shape[0]
        if len(df) > hru_count:
            df = df.iloc[:-hru_count].copy()
            LOG.info("Dropped %s trailing monthly summary rows", hru_count)
        marker = df["mon"].astype(str)
        annual = df[marker.str.len() == 4].copy()
        monthly = df[df["mon"].isin(range(1, 13))].copy().reset_index(drop=True)
        years = annual["mon"].drop_duplicates().astype(int).tolist()

        if not years:
            start_year = read_simulation_start(file_cio)
            frame_count = len(monthly) // max(hru_count * 12, 1)
            years = list(range(start_year, start_year + frame_count))

        expected = len(years) * hru_count * 12
        if expected != len(monthly):
            raise ValueError(f"Monthly row count mismatch: expected {expected}, got {len(monthly)}")

        repeated_years = pd.Series(years).repeat(hru_count * 12).reset_index(drop=True)
        monthly["sim_year"] = repeated_years.astype(int)
        monthly["sim_mon"] = monthly["mon"].astype(int)
        monthly["sim_day"] = 1
        monthly["sim_time"] = pd.to_datetime(
            monthly["sim_year"].astype(str) + "-" + monthly["sim_mon"].astype(str) + "-01"
        ).dt.date
        monthly["mon"] = pd.to_datetime(monthly["sim_time"]).dt.strftime("%Y-%m")

        if annual.empty:
            return monthly
        annual["iprint"] = 2
        annual["sim_year"] = annual["mon"].astype(int)
        annual["sim_mon"] = 1
        annual["sim_day"] = 1
        annual["sim_time"] = pd.to_datetime(annual["sim_year"].astype(str) + "-01-01").dt.date
        annual["mon"] = annual["sim_year"].astype(str)
        return pd.concat([monthly, annual], ignore_index=True, sort=False)

    if iprint == 1:
        hru_count = df["hru"].drop_duplicates().shape[0]
        start_year = read_simulation_start(file_cio)
        day_count = len(df) // max(hru_count, 1)
        dates = pd.date_range(start=f"{start_year}-01-01", periods=day_count, freq="D")
        if len(dates) * hru_count != len(df):
            raise ValueError("Daily row count is not divisible by HRU count")
        repeated_dates = pd.Series(dates).repeat(hru_count).reset_index(drop=True)
        df["sim_time"] = repeated_dates.dt.date
        df["sim_year"] = repeated_dates.dt.year
        df["sim_mon"] = repeated_dates.dt.month
        df["sim_day"] = repeated_dates.dt.day
        df["mon"] = repeated_dates.dt.strftime("%Y-%m-%d")
        return df

    marker = df["mon"].astype(str)
    yearly = df[marker.str.len() == 4].copy()
    yearly["sim_year"] = yearly["mon"].astype(int)
    yearly["sim_mon"] = 1
    yearly["sim_day"] = 1
    yearly["sim_time"] = pd.to_datetime(yearly["sim_year"].astype(str) + "-01-01").dt.date
    yearly["mon"] = yearly["sim_year"].astype(str)
    return yearly


def parse_hru_output(swat_dir: str | Path) -> pd.DataFrame:
    swat_dir = Path(swat_dir)
    hru_file = swat_dir / "output.hru"
    file_cio = swat_dir / "file.cio"
    if not hru_file.exists():
        raise FileNotFoundError(f"output.hru not found: {hru_file}")
    if not file_cio.exists():
        raise FileNotFoundError(f"file.cio not found: {file_cio}")

    iprint = read_iprint(file_cio)
    df = read_hru_strict_frame(hru_file)
    LOG.info("Strict fixed-width parser loaded %s HRU rows", len(df))
    df = cast_hru_frame(df)
    df["mon"] = pd.to_numeric(df["mon"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["mon", "hru", "gis"]).copy()
    df = add_time_columns(df, iprint, file_cio)
    df = cast_hru_frame(df)
    return df


def clean_json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def import_aoi(cfg: dict[str, Any]) -> int:
    task = cfg["task"]
    publish = cfg.get("publish", {})
    db_cfg = cfg["database"]
    task_name = str(task["name"])
    shp_path = Path(task["aoi_shapefile"])
    table = qname(publish.get("aoi_table", "public.swat_aoi_vector"))
    srid = int(publish.get("srid", DEFAULT_SRID))
    hru_field = str(task.get("hru_id_field", "hrugis")).lower()

    if not shp_path.exists():
        raise FileNotFoundError(f"AOI shapefile not found: {shp_path}")

    LOG.info("Reading AOI polygons from %s", shp_path)
    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        raise ValueError("AOI shapefile is empty")
    gdf.columns = [str(c).lower() for c in gdf.columns]
    if hru_field not in gdf.columns:
        raise ValueError(f"AOI shapefile missing HRU id field: {hru_field}")

    if gdf.crs is None:
        LOG.warning("AOI shapefile has no CRS; assuming EPSG:%s", srid)
        gdf = gdf.set_crs(epsg=srid)
    elif gdf.crs.to_epsg() != srid:
        gdf = gdf.to_crs(epsg=srid)

    geom_name = gdf.geometry.name
    rows = []
    for _, row in gdf.iterrows():
        geom = row[geom_name]
        if geom is None or geom.is_empty:
            continue
        props = {
            str(k): clean_json_value(v)
            for k, v in row.drop(labels=[geom_name]).to_dict().items()
        }
        rows.append((task_name, str(row[hru_field]), Json(props), psycopg2.Binary(geom.wkb), srid, str(shp_path)))

    if not rows:
        raise ValueError("No valid AOI geometries found")

    insert_sql = f"""
        INSERT INTO {table} (task_name, hru_gis, properties, geom, source_file)
        VALUES %s
    """
    template = (
        "(%s, %s, %s, "
        "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%s), %s)), 3)), %s)"
    )
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE task_name = %s", (task_name,))
        execute_values(cur, insert_sql, rows, template=template, page_size=1000)
    LOG.info("Imported %s AOI polygons for task %s", len(rows), task_name)
    return len(rows)


def import_hru(cfg: dict[str, Any]) -> int:
    task = cfg["task"]
    publish = cfg.get("publish", {})
    db_cfg = cfg["database"]
    task_name = str(task["name"])
    table_name = publish.get("hru_table", "public.swat_hru_timeseries")
    table = qname(table_name)
    swat_dir = Path(task["swat_dir"])

    LOG.info("Parsing HRU output from %s", swat_dir)
    df = parse_hru_output(swat_dir)
    df["task_name"] = task_name

    columns = [c for c in df.columns if c in table_columns(db_cfg, table_name)]
    if "task_name" not in columns:
        columns.append("task_name")
    df = df[columns].copy()
    df = df.replace({np.nan: None})

    rows = [tuple(clean_json_value(v) for v in row) for row in df.itertuples(index=False, name=None)]
    if not rows:
        raise ValueError("No HRU rows parsed")

    cols_sql = ", ".join(f'"{c}"' for c in columns)
    insert_sql = f"INSERT INTO {table} ({cols_sql}) VALUES %s"
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE task_name = %s", (task_name,))
        execute_values(cur, insert_sql, rows, page_size=5000)
    LOG.info("Imported %s HRU time-series rows for task %s", len(rows), task_name)
    return len(rows)


def table_columns(db_cfg: dict[str, Any], table_name: str) -> set[str]:
    schema, table = split_table_name(table_name)
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        return {row[0] for row in cur.fetchall()}


def split_table_name(table_name: str) -> tuple[str, str]:
    require_table_name(table_name, "table")
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        return schema, table
    return "public", table_name


class GeoServerPublisher:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(username, password)
        self.timeout = timeout
        self.json_headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def get(self, path: str):
        return requests.get(
            f"{self.base_url}{path}",
            headers=self.json_headers,
            auth=self.auth,
            timeout=self.timeout,
        )

    def post_json(self, path: str, body: dict[str, Any]):
        return requests.post(
            f"{self.base_url}{path}",
            data=json.dumps(body),
            headers=self.json_headers,
            auth=self.auth,
            timeout=self.timeout,
        )

    def put_json(self, path: str, body: dict[str, Any]):
        return requests.put(
            f"{self.base_url}{path}",
            data=json.dumps(body),
            headers=self.json_headers,
            auth=self.auth,
            timeout=self.timeout,
        )

    def post_xml(self, path: str, body: str):
        return requests.post(
            f"{self.base_url}{path}",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            auth=self.auth,
            timeout=self.timeout,
        )

    def put_sld(self, path: str, body: str):
        return requests.put(
            f"{self.base_url}{path}",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/vnd.ogc.sld+xml"},
            auth=self.auth,
            timeout=self.timeout,
        )

    def delete(self, path: str):
        return requests.delete(f"{self.base_url}{path}", auth=self.auth, timeout=self.timeout)

    @staticmethod
    def ok(response, expected: tuple[int, ...]) -> None:
        if response.status_code not in expected:
            raise RuntimeError(f"GeoServer HTTP {response.status_code}: {response.text[:800]}")

    def ensure_workspace(self, workspace: str) -> None:
        response = self.get(f"/rest/workspaces/{workspace}.json")
        if response.status_code == 200:
            return
        response = self.post_json("/rest/workspaces", {"workspace": {"name": workspace}})
        self.ok(response, (201, 409))

    def ensure_datastore(self, workspace: str, datastore: str, db_cfg: dict[str, Any], schema: str) -> None:
        response = self.get(f"/rest/workspaces/{workspace}/datastores/{datastore}.json")
        if response.status_code == 200:
            return
        body = {
            "dataStore": {
                "name": datastore,
                "type": "PostGIS",
                "enabled": True,
                "workspace": {"name": workspace},
                "connectionParameters": {
                    "entry": [
                        {"@key": "host", "$": db_cfg.get("host", "localhost")},
                        {"@key": "port", "$": str(db_cfg.get("port", 5432))},
                        {"@key": "database", "$": db_cfg.get("database", "postgres")},
                        {"@key": "user", "$": db_cfg.get("user", "postgres")},
                        {"@key": "passwd", "$": db_cfg.get("password", "")},
                        {"@key": "dbtype", "$": "postgis"},
                        {"@key": "schema", "$": schema},
                        {"@key": "Expose primary keys", "$": "true"},
                    ]
                },
            }
        }
        response = self.post_json(f"/rest/workspaces/{workspace}/datastores", body)
        self.ok(response, (201,))

    def publish_sql_view(
        self,
        workspace: str,
        datastore: str,
        layer_name: str,
        sql: str,
        default_time: str,
        default_scale: str,
        srid: int,
        default_style: str,
    ) -> None:
        existing = self.get(f"/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes/{layer_name}.json")
        if existing.status_code == 200:
            response = self.delete(
                f"/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes/{layer_name}?recurse=true"
            )
            self.ok(response, (200, 202, 404))

        virtual_table = {
            "name": layer_name,
            "sql": sql,
            "escapeSql": False,
            "geometry": {"name": "geom", "type": "MultiPolygon", "srid": srid},
            "parameter": [
                {
                    "name": "sim_time",
                    "defaultValue": default_time,
                    "regexpValidator": r"^\d{4}-\d{2}-\d{2}$",
                },
                {
                    "name": "scale",
                    "defaultValue": default_scale,
                    "regexpValidator": r"^(daily|monthly|yearly)$",
                },
            ],
        }
        body = {
            "featureType": {
                "name": layer_name,
                "title": layer_name,
                "enabled": True,
                "srs": f"EPSG:{srid}",
                "metadata": {
                    "entry": [
                        {"@key": "JDBC_VIRTUAL_TABLE", "virtualTable": virtual_table},
                    ]
                },
            }
        }
        response = self.post_json(f"/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes", body)
        self.ok(response, (201,))
        self.set_default_style(workspace, layer_name, default_style)

    def upsert_style(self, workspace: str, style_name: str, sld: str) -> None:
        existing = self.get(f"/rest/workspaces/{workspace}/styles/{style_name}.json")
        if existing.status_code == 404:
            style_xml = (
                f"<style><name>{xml_text(style_name)}</name>"
                f"<filename>{xml_text(style_name)}.sld</filename></style>"
            )
            response = self.post_xml(f"/rest/workspaces/{workspace}/styles", style_xml)
            if response.status_code not in (200, 201, 409):
                raise RuntimeError(f"GeoServer style create failed: HTTP {response.status_code}: {response.text[:400]}")
        elif existing.status_code != 200:
            self.ok(existing, (200,))

        response = self.put_sld(f"/rest/workspaces/{workspace}/styles/{style_name}.sld", sld)
        if response.status_code not in (200, 201):
            fallback = self.put_sld(f"/rest/workspaces/{workspace}/styles/{style_name}", sld)
            if fallback.status_code not in (200, 201):
                detail = response.text[:800] or fallback.text[:800]
                raise RuntimeError(
                    f"GeoServer style upload failed: "
                    f".sld HTTP {response.status_code}; style HTTP {fallback.status_code}; {detail}"
                )

    def set_default_style(self, workspace: str, layer_name: str, style_name: str) -> None:
        body = {"layer": {"defaultStyle": {"name": style_name, "workspace": workspace}}}
        response = self.put_json(f"/rest/layers/{workspace}:{layer_name}", body)
        self.ok(response, (200,))

    def bbox(self, workspace: str, datastore: str, layer_name: str) -> str | None:
        response = self.get(f"/rest/workspaces/{workspace}/datastores/{datastore}/featuretypes/{layer_name}.json")
        if response.status_code != 200:
            return None
        feature_type = response.json().get("featureType", {})
        bbox = feature_type.get("latLonBoundingBox") or feature_type.get("nativeBoundingBox")
        if not bbox:
            return None
        return f"{bbox['minx']},{bbox['miny']},{bbox['maxx']},{bbox['maxy']}"


def compute_levels(values: list[float], bins: int, method: str) -> list[float]:
    data = np.asarray(values, dtype=float)
    data = data[~np.isnan(data)]
    if data.size == 0:
        return [0.0] * bins
    data_min = float(np.min(data))
    data_max = float(np.max(data))
    if data_min == data_max:
        return [round(data_max + (i - bins + 1) * 1e-6, 6) for i in range(bins)]
    method = method.lower()
    if method in {"quantile", "equal_frequency"}:
        levels = np.percentile(data, np.linspace(0, 100, bins + 1)[1:])
    else:
        levels = np.linspace(data_min, data_max, bins + 1)[1:]
    out = [round(float(v), 6) for v in levels]
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = round(out[i - 1] + 1e-6, 6)
    return out


def xml_text(value: Any) -> str:
    return xml_escape(str(value), {'"': "&quot;", "'": "&apos;"})


def simulation_config(
    db_cfg: dict[str, Any],
    hru_table: str,
    task_name: str,
    variable: str,
    bins: int,
    method: str,
) -> list[dict[str, Any]]:
    require_column_name(variable, "variable")
    table = qname(hru_table)
    scales = []
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        for iprint, scale_name in TIME_SCALE_BY_IPRINT.items():
            cur.execute(
                f"""
                SELECT MIN(sim_time), MAX(sim_time), COUNT(DISTINCT sim_time)
                FROM {table}
                WHERE task_name = %s AND iprint = %s
                """,
                (task_name, iprint),
            )
            min_time, max_time, duration = cur.fetchone()
            if not duration:
                continue
            cur.execute(
                f"""
                SELECT "{variable}"
                FROM {table}
                WHERE task_name = %s AND iprint = %s AND "{variable}" IS NOT NULL
                """,
                (task_name, iprint),
            )
            values = [row[0] for row in cur.fetchall()]
            scales.append(
                {
                    "time": [min_time.strftime("%Y-%m-%d"), max_time.strftime("%Y-%m-%d")],
                    "layers": "",
                    "styles": "",
                    "levels": compute_levels(values, bins=bins, method=method),
                    "scale": scale_name,
                    "duration": int(duration),
                }
            )
    if not scales:
        raise ValueError(f"No time scales found for task {task_name}")
    return scales


def sld_style(style_name: str, variable: str, levels: list[float], colors: list[str]) -> str:
    rules = []
    for idx, (level, color) in enumerate(zip(levels, colors)):
        if idx == 0:
            title = f"<= {level:.3f}"
            filter_xml = f"""
          <ogc:PropertyIsLessThanOrEqualTo>
            <ogc:PropertyName>{variable}</ogc:PropertyName>
            <ogc:Literal>{level}</ogc:Literal>
          </ogc:PropertyIsLessThanOrEqualTo>"""
        else:
            prev = levels[idx - 1]
            title = f"{prev:.3f} - {level:.3f}"
            filter_xml = f"""
          <ogc:And>
            <ogc:PropertyIsGreaterThan>
              <ogc:PropertyName>{variable}</ogc:PropertyName>
              <ogc:Literal>{prev}</ogc:Literal>
            </ogc:PropertyIsGreaterThan>
            <ogc:PropertyIsLessThanOrEqualTo>
              <ogc:PropertyName>{variable}</ogc:PropertyName>
              <ogc:Literal>{level}</ogc:Literal>
            </ogc:PropertyIsLessThanOrEqualTo>
          </ogc:And>"""
        rules.append(
            f"""
        <Rule>
          <Title>{xml_text(title)}</Title>
          <ogc:Filter>{filter_xml}
          </ogc:Filter>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">{color}</CssParameter>
              <CssParameter name="fill-opacity">0.92</CssParameter>
            </Fill>
            <Stroke>
              <CssParameter name="stroke">{color}</CssParameter>
              <CssParameter name="stroke-width">0.2</CssParameter>
            </Stroke>
          </PolygonSymbolizer>
        </Rule>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
  xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>{xml_text(style_name)}</Name>
    <UserStyle>
      <Title>{xml_text(style_name)}</Title>
      <FeatureTypeStyle>
{''.join(rules)}
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>"""


def default_colors(bins: int) -> list[str]:
    palette = [
        "#053061", "#2166AC", "#4393C3", "#92C5DE", "#D1E5F0",
        "#FDDBC7", "#F4A582", "#D6604D", "#B2182B", "#67001F",
    ]
    if bins == len(palette):
        return palette
    start = np.array([5, 48, 97], dtype=float)
    end = np.array([103, 0, 31], dtype=float)
    colors = []
    for i in range(bins):
        ratio = i / max(bins - 1, 1)
        rgb = (start + (end - start) * ratio).astype(int)
        colors.append("#%02X%02X%02X" % tuple(rgb))
    return colors


def build_sql_view(variable: str, task_name: str, aoi_table: str, hru_table: str) -> str:
    variable = require_column_name(variable, "variable")
    task_sql = sql_literal(task_name)
    return f"""
SELECT
    a.id AS id,
    a.geom AS geom,
    h."{variable}" AS "{variable}"
FROM {qname(aoi_table)} a
JOIN {qname(hru_table)} h
  ON h.gis = a.hru_gis
WHERE a.task_name = {task_sql}
  AND h.task_name = {task_sql}
  AND h.sim_time = DATE '%sim_time%'
  AND h.iprint = CASE
      WHEN '%scale%' = 'daily' THEN 1
      WHEN '%scale%' = 'monthly' THEN 0
      WHEN '%scale%' = 'yearly' THEN 2
      ELSE 2
  END
  AND h."{variable}" IS NOT NULL
""".strip()


def db_bbox(db_cfg: dict[str, Any], aoi_table: str, task_name: str) -> str:
    with pg_connect(db_cfg) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
            FROM (
                SELECT ST_Extent(geom) AS e
                FROM {qname(aoi_table)}
                WHERE task_name = %s
            ) s
            """,
            (task_name,),
        )
        row = cur.fetchone()
    if not row or any(v is None for v in row):
        return "-180,-90,180,90"
    return ",".join(str(float(v)) for v in row)


def image_size_from_bbox(bbox: str, max_px: int = 1000) -> tuple[int, int]:
    minx, miny, maxx, maxy = [float(v) for v in bbox.split(",")]
    width = max(maxx - minx, 1e-9)
    height = max(maxy - miny, 1e-9)
    ratio = width / height
    if ratio >= 1:
        return max_px, max(1, int(round(max_px / ratio)))
    return max(1, int(round(max_px * ratio))), max_px


def build_display_entry(
    access_url: str,
    workspace: str,
    layer_name: str,
    style_name: str,
    bbox: str,
    srid: int,
    scales: list[dict[str, Any]],
    default_scale: str,
) -> dict[str, Any]:
    width, height = image_size_from_bbox(bbox)
    default_time = next((s["time"][0] for s in scales if s["scale"] == default_scale), scales[0]["time"][0])
    return {
        "url_info": {
            "base_url": f"{access_url.rstrip('/')}/{workspace}/wms",
            "service": "WMS",
            "version": "1.1.0",
            "request": "GetMap",
            "layers": f"{workspace}:{layer_name}",
            "styles": f"{workspace}:{style_name}",
            "crs": "",
            "srs": f"EPSG:{srid}",
            "bbox": bbox,
            "width": width,
            "height": height,
            "format": "image/png",
            "transparent": "true",
            "bgcolor": "0x000000",
            "exceptions": "",
            "time": "",
            "elevation": "",
            "dimensions": {},
            "cql_filter": "",
            "filter": "",
            "featureid": "",
            "sld": "",
            "sld_body": "",
            "sld_version": "",
            "angle": "",
            "buffer": "",
            "ratio": "",
            "clip": "",
            "scale": "",
            "map_resolution": "",
            "dpi": "",
            "format_options": "",
            "tiled": "",
            "tilesorigin": "",
            "tilesize": "",
            "sortBy": "",
            "palette": "",
            "interpolations": "",
            "env": {},
            "viewparams": {"sim_time": default_time, "scale": default_scale},
            "content-disposition": "",
            "filename": "",
            "custom_params": {},
        },
        "scales_info": scales,
    }


def publish(cfg: dict[str, Any]) -> dict[str, Any]:
    task = cfg["task"]
    publish_cfg = cfg.get("publish", {})
    geoserver_cfg = cfg["geoserver"]
    db_cfg = cfg["database"]

    task_name = str(task["name"])
    variables = task.get("variables", [])
    if isinstance(variables, str):
        variables = [v for v in re.split(r"[,\s]+", variables) if v]
    if not variables:
        raise ValueError("task.variables is empty")

    workspace = publish_cfg.get("workspace", "swat")
    datastore = publish_cfg.get("datastore", "swat_postgis")
    aoi_table = publish_cfg.get("aoi_table", "public.swat_aoi_vector")
    hru_table = publish_cfg.get("hru_table", "public.swat_hru_timeseries")
    schema, _ = split_table_name(hru_table)
    srid = int(publish_cfg.get("srid", DEFAULT_SRID))
    bins = int(publish_cfg.get("class_bins", 10))
    method = str(publish_cfg.get("class_method", "quantile"))
    default_scale = str(publish_cfg.get("default_scale", "yearly"))
    access_url = geoserver_cfg.get("access_url") or geoserver_cfg["url"]

    publisher = GeoServerPublisher(
        geoserver_cfg["url"],
        geoserver_cfg.get("user", "admin"),
        geoserver_cfg.get("password", "geoserver"),
        int(geoserver_cfg.get("timeout", 60)),
    )
    publisher.ensure_workspace(workspace)
    publisher.ensure_datastore(workspace, datastore, db_cfg, schema)

    display_config = {}
    available_columns = table_columns(db_cfg, hru_table)
    bbox = db_bbox(db_cfg, aoi_table, task_name)
    colors = default_colors(bins)

    for variable in variables:
        variable = require_column_name(str(variable).lower(), "variable")
        if variable not in available_columns:
            raise ValueError(f"Variable {variable!r} is not a column in {hru_table}")
        layer_name = slug(f"{variable.upper()}-{task_name.upper()}")
        scales = simulation_config(db_cfg, hru_table, task_name, variable, bins, method)

        default_style = ""
        for scale_info in scales:
            style_name = slug(f"{variable.upper()}-{task_name.upper()}-{scale_info['scale'].upper()}")
            sld = sld_style(style_name, variable, scale_info["levels"], colors)
            publisher.upsert_style(workspace, style_name, sld)
            scale_info["layers"] = layer_name
            scale_info["styles"] = style_name
            if scale_info["scale"] == default_scale:
                default_style = style_name

        variable_default_scale = default_scale
        if not default_style:
            variable_default_scale = scales[0]["scale"]
            default_style = scales[0]["styles"]

        sql = build_sql_view(variable, task_name, aoi_table, hru_table)
        default_time = next(s for s in scales if s["scale"] == variable_default_scale)["time"][0]
        publisher.publish_sql_view(
            workspace,
            datastore,
            layer_name,
            sql,
            default_time=default_time,
            default_scale=variable_default_scale,
            srid=srid,
            default_style=default_style,
        )
        geoserver_bbox = publisher.bbox(workspace, datastore, layer_name) or bbox
        display_config[variable] = build_display_entry(
            access_url, workspace, layer_name, default_style, geoserver_bbox, srid, scales, variable_default_scale
        )
        LOG.info("Published %s:%s", workspace, layer_name)

    return display_config


def write_display_config(js_path: str | Path, display_config: dict[str, Any]) -> None:
    path = Path(js_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "// GeoServer WMS configuration generated by swat_vector_time_pipeline.py\n"
    content += "const GEOSERVER_CONFIG = "
    content += json.dumps(display_config, ensure_ascii=False, indent=4)
    content += ";\n"
    path.write_text(content, encoding="utf-8")
    LOG.info("Wrote display config: %s", path)


def run_pipeline(cfg: dict[str, Any], args: argparse.Namespace) -> None:
    schema_sql = args.schema_sql or cfg.get("schema_sql") or DEFAULT_SCHEMA_SQL
    if args.init_db or cfg.get("initialize_schema", True):
        init_schema(cfg["database"], schema_sql)
    if not args.skip_import:
        import_aoi(cfg)
        import_hru(cfg)
    if args.skip_geoserver:
        return
    display_config = publish(cfg)
    output_cfg = cfg.get("output", {})
    js_path = args.display_config or output_cfg.get("geoserver_config_js")
    if js_path and not args.skip_display_config:
        write_display_config(js_path, display_config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SWAT vector time rendering pipeline")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="Path to the YAML config file")
    parser.add_argument("--schema-sql", default=None, help="Path to the PostGIS schema SQL")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database schema before running")
    parser.add_argument("--skip-import", action="store_true", help="Reuse existing task rows in PostGIS")
    parser.add_argument("--skip-geoserver", action="store_true", help="Only initialize/import data")
    parser.add_argument("--skip-display-config", action="store_true", help="Do not write geoserver_config.js")
    parser.add_argument("--display-config", default=None, help="Output path for geoserver_config.js")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_yaml(args.config)
    configure_logging(cfg)
    run_pipeline(cfg, args)


if __name__ == "__main__":
    main()
