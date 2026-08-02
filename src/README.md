# SWATVIS: SWAT Vector Time Pipeline

SWATVIS is a Python workflow for publishing Hydrological Response Unit (HRU)
output from the Soil and Water Assessment Tool (SWAT) as interactive,
time-selectable web maps. It imports HRU geometry and `output.hru` records into
PostgreSQL/PostGIS, creates parameterized GeoServer SQL Views and SLD styles,
and generates the configuration used by the included OpenLayers viewer.

The complete workflow is executed with one command:

```text
SWAT HRU shapefile + output.hru + file.cio
                    |
                    v
             Python pipeline
                    |
         +----------+-----------+
         |                      |
         v                      v
  PostgreSQL/PostGIS       GeoServer
  geometry + time series   SQL Views + SLD
         |                      |
         +----------+-----------+
                    v
          OpenLayers WMS viewer
```

## Main features

- Parses the fixed-width SWAT `output.hru` format implemented in this release.
- Derives discrete daily, monthly, or yearly simulation dates from `file.cio`
  and `output.hru`.
- Imports HRU polygons and normalized time-series records into PostGIS.
- Reprojects HRU geometry to the configured target EPSG code when required.
- Publishes one parameterized GeoServer SQL View per selected variable.
- Generates a separate quantile or equal-interval SLD for every available
  variable/time-scale combination.
- Generates `result_display/geoserver_config.js` for the reusable OpenLayers
  viewer.
- Replaces data for a named task on rerun, allowing a publication to be
  reproduced without manually deleting old task records.

## Repository contents

| Path | Purpose |
|---|---|
| `swat_vector_time_pipeline.py` | Main command-line import and publication pipeline |
| `swat_vector_time_config.example.yaml` | Public configuration template without credentials |
| `sql/postgresql/swat_vector_time_schema.sql` | PostGIS tables, indexes, and time-field trigger |
| `result_display/index.html` | OpenLayers browser interface |
| `result_display/app_wms.js` | Viewer and WMS time-navigation logic |
| `result_display/ol.js`, `result_display/ol.css` | Local OpenLayers fallback assets |
| `environment.yml` | Reproducible Conda environment |

`swat_vector_time_config.yaml` and the generated
`result_display/geoserver_config.js` are deployment-specific files. Do not
publish them when they contain private hosts, user names, or credentials.

## Requirements

### External services

The following services must be running before the pipeline is executed:

- PostgreSQL with the PostGIS and `pgcrypto` extensions;
- GeoServer with REST API access and PostGIS datastore support;
- a user able to create the required PostGIS extensions, tables, indexes,
  function, and trigger when `initialize_schema: true`;
- a GeoServer account able to create or update workspaces, datastores, feature
  types, layers, and styles.

The database must be reachable from both the computer running the Python
pipeline and the GeoServer host. A value such as `localhost` in the database
configuration refers to the Python host when Python connects, but the datastore
created in GeoServer must also be able to resolve and reach that host. This is
especially important when GeoServer or PostgreSQL runs in Docker.

The reported SoftwareX case study was tested with:

- Python 3.12.11 in the local `hydrolib` environment;
- PostgreSQL 15.8 and PostGIS 3.4.3;
- GeoServer 2.28.4;
- GeoPandas 1.1.1, NumPy 2.4.2, pandas 2.3.1, PyYAML 6.0.3,
  psycopg2 2.9.12, and Requests 2.32.4.

For reproducible installation from this repository, `environment.yml` defines
the supported Python 3.10 environment and its pinned direct dependencies.

### SWAT inputs

Two SWAT model files and one GIS dataset are required:

1. `output.hru`, containing the HRU output records;
2. `file.cio`, from the same SWAT simulation, containing the output interval
   (`IPRINT`) and simulation start year;
3. an ESRI Shapefile containing the HRU polygons.

Keep all Shapefile sidecar files together, normally `.shp`, `.shx`, `.dbf`, and
`.prj`. The attribute configured by `task.hru_id_field` must identify the same
GIS HRU code stored in the `GIS` field of `output.hru`. The example configuration
uses `hrugis`.

This release implements a specific classic SWAT fixed-width `output.hru`
layout. Check that the field positions match `HRU_MANUAL_FIELDS` and
`HRU_MANUAL_COLSPECS` in the pipeline before using output produced by another
SWAT version or a customized output format. SWAT+ files are not supported.

## Installation

### 1. Obtain the source code

Clone the public repository and enter its root directory:

```bash
git clone <PUBLIC-REPOSITORY-URL>.git
cd swat-postproc
```

For an archived SoftwareX release, use the version tag or DOI stated in the
article rather than an unreleased development branch.

### 2. Install Conda

Install Miniconda, Anaconda, or Miniforge if `conda` is not already available.
Then create the pinned environment:

```bash
conda env create -f environment.yml
conda activate swat-postproc-env
```

To synchronize an existing environment with the repository definition:

```bash
conda env update -f environment.yml --prune
```

Confirm the installation:

```bash
python --version
python -c "import geopandas, numpy, pandas, psycopg2, requests, yaml; print('Dependencies OK')"
```

No Python package installation step is required: the pipeline is run directly
from the repository root.

## Service preparation

### PostgreSQL/PostGIS

Create an empty database or select an existing database in which the configured
user may create the SWATVIS objects. For example, using an administrative
PostgreSQL account:

```sql
CREATE DATABASE swat;
```

By default the pipeline executes
`sql/postgresql/swat_vector_time_schema.sql`. The script uses `IF NOT EXISTS`
where appropriate and creates:

- extensions `postgis` and `pgcrypto`;
- table `public.swat_aoi_vector`;
- table `public.swat_hru_timeseries`;
- spatial, join, and time indexes;
- a trigger that fills normalized time fields.

If the runtime database user cannot create extensions, a database administrator
must install `postgis` and `pgcrypto` first. The schema can also be initialized
separately with a suitable PostgreSQL client, after which
`initialize_schema: false` may be used.

### GeoServer

1. Start GeoServer and verify that its REST endpoint is accessible, for example
   `http://localhost:8080/geoserver/rest/about/version.json`.
2. Ensure that the GeoServer installation supports PostgreSQL/PostGIS
   datastores.
3. Ensure that the configured GeoServer account has publication permissions.
4. Ensure that GeoServer can connect to the same PostgreSQL database specified
   in the YAML file.

The workspace and datastore do not need to be created manually. The pipeline
creates or reuses them and then publishes the SQL Views and styles.

## Configuration

Copy the public template to a private runtime configuration:

```powershell
Copy-Item swat_vector_time_config.example.yaml swat_vector_time_config.yaml
```

On Linux or macOS, use:

```bash
cp swat_vector_time_config.example.yaml swat_vector_time_config.yaml
```

Edit `swat_vector_time_config.yaml`. Do not commit this file when it contains
real credentials.

### Configuration reference

| Key | Required | Meaning |
|---|---:|---|
| `initialize_schema` | No | Run the schema SQL before import; default behavior is enabled |
| `schema_sql` | No | Path to the PostGIS schema script |
| `logging.level` | No | Python logging level, normally `INFO` |
| `task.name` | Yes | Stable task identifier stored in PostGIS and used in GeoServer resource names |
| `task.aoi_shapefile` | Yes | Path to the HRU polygon `.shp` file |
| `task.swat_dir` | Yes | Directory containing `output.hru` and `file.cio` |
| `task.hru_id_field` | No | HRU GIS identifier column in the Shapefile; default `hrugis` |
| `task.variables` | Yes | `output.hru` columns to publish, for example `surq_gen` and `syld` |
| `database.host` | Yes | PostgreSQL host reachable by Python and GeoServer |
| `database.port` | Yes | PostgreSQL port, normally `5432` |
| `database.database` | Yes | PostgreSQL database name |
| `database.user` | Yes | PostgreSQL user |
| `database.password` | Yes | PostgreSQL password; keep private |
| `database.sslmode` | No | psycopg2 SSL mode, for example `prefer` or `require` |
| `geoserver.url` | Yes | GeoServer base URL used by the REST publisher |
| `geoserver.access_url` | No | Browser-accessible GeoServer base URL; defaults to `url` |
| `geoserver.user` | Yes | GeoServer REST user |
| `geoserver.password` | Yes | GeoServer REST password; keep private |
| `geoserver.timeout` | No | REST request timeout in seconds |
| `publish.workspace` | No | GeoServer workspace; default `swat` |
| `publish.datastore` | No | GeoServer datastore; default `swat_postgis` |
| `publish.aoi_table` | No | Qualified PostGIS geometry table |
| `publish.hru_table` | No | Qualified PostGIS time-series table |
| `publish.srid` | No | Target geometry EPSG code; schema supplied here uses `4326` |
| `publish.class_bins` | No | Number of SLD classes; default `10` |
| `publish.class_method` | No | `quantile` or `equal_interval` |
| `publish.default_scale` | No | Initial scale: `daily`, `monthly`, or `yearly` when present |
| `output.geoserver_config_js` | No | Generated viewer configuration path |

Variable names are converted to lowercase and must correspond to columns in
`public.swat_hru_timeseries`. Table and column identifiers are validated before
they are inserted into SQL.

The schema supplied with this release declares geometry as
`geometry(MultiPolygon, 4326)`. Keep `publish.srid: 4326` unless the schema is
deliberately changed to another SRID as well.

## Running the pipeline

All commands below must be executed from the repository root with the Conda
environment activated.

### Complete workflow

```bash
python swat_vector_time_pipeline.py -c swat_vector_time_config.yaml
```

The command performs the following operations in order:

1. initializes the PostGIS schema when enabled;
2. deletes and replaces HRU geometries for `task.name`;
3. parses `output.hru`, then deletes and replaces time-series records for the
   same task;
4. creates or updates the GeoServer workspace and PostGIS datastore;
5. generates scale-specific SLD styles;
6. creates or updates one parameterized SQL View layer per variable;
7. writes the OpenLayers client configuration.

Rerunning a task is intentionally replace-in-place. Records belonging to other
task names are not deleted.

### Command-line options

```text
-c, --config PATH            YAML configuration file
--schema-sql PATH            Override the configured schema SQL path
--init-db                    Initialize the schema even if disabled in YAML
--skip-import                Reuse existing task records in PostGIS
--skip-geoserver             Stop after schema initialization/import
--skip-display-config        Do not write the browser configuration
--display-config PATH        Override the browser configuration output path
```

Examples:

```bash
# Import data without publishing to GeoServer
python swat_vector_time_pipeline.py -c swat_vector_time_config.yaml --skip-geoserver

# Republish existing database records after changing styles or publication settings
python swat_vector_time_pipeline.py -c swat_vector_time_config.yaml --skip-import

# Write the viewer configuration to an alternative path
python swat_vector_time_pipeline.py -c swat_vector_time_config.yaml \
  --display-config result_display/geoserver_config.js
```

## Expected output

With variables `surq_gen` and `syld`, monthly and yearly records, task name
`yanjiga`, workspace `swat`, and 10 classes, the run creates or updates:

- 364 HRU geometries and the valid parsed time-series records in PostGIS for
  the case-study dataset;
- SQL View layers `SURQ_GEN-YANJIGA` and `SYLD-YANJIGA`;
- styles `SURQ_GEN-YANJIGA-MONTHLY`, `SURQ_GEN-YANJIGA-YEARLY`,
  `SYLD-YANJIGA-MONTHLY`, and `SYLD-YANJIGA-YEARLY`;
- `result_display/geoserver_config.js`.

Resource counts depend on the selected variables and scales actually found in
the database: one SQL View layer is published per variable and one SLD is
published per variable/time-scale combination.

The SQL View accepts two validated GeoServer `viewparams`:

- `sim_time`: an existing date in `YYYY-MM-DD` format;
- `scale`: `daily`, `monthly`, or `yearly`.

The request retrieves a discrete database time step. It does not interpolate
between dates.

## Opening the viewer

After a successful pipeline run, serve the viewer through a local web server:

```bash
python -m http.server 8000 --directory result_display
```

Open <http://localhost:8000/> in a web browser. Keep the terminal running while
using the viewer.

The interface provides:

- variable and temporal-scale selection;
- a discrete timeline slider;
- previous, next, play, and pause controls;
- a dynamically populated class legend;
- map zoom, extent reset, and base-map switching.

The included client currently generates monthly and yearly frame sequences.
Although the backend can import and publish daily records, daily timeline
generation is not implemented in this viewer version. The current interface
also contains explicit labels and palettes for `SURQ_GEN` and `SYLD`; publishing
another database variable requires corresponding client presentation metadata.

If the viewer is opened from another computer, `geoserver.access_url` must be a
URL reachable by that browser. Do not use `localhost` unless GeoServer runs on
the same computer as the browser.

## Verification

### Check imported record counts

Run these read-only SQL queries using a PostgreSQL client, replacing `yanjiga`
with the configured task name:

```sql
SELECT COUNT(*) AS geometry_count
FROM public.swat_aoi_vector
WHERE task_name = 'yanjiga';

SELECT iprint, COUNT(*) AS record_count,
       COUNT(DISTINCT sim_time) AS time_step_count,
       MIN(sim_time) AS first_time, MAX(sim_time) AS last_time
FROM public.swat_hru_timeseries
WHERE task_name = 'yanjiga'
GROUP BY iprint
ORDER BY iprint;
```

`iprint` values map to scales as follows: `0 = monthly`, `1 = daily`, and
`2 = yearly`.

### Check GeoServer

1. Open the GeoServer web administration interface.
2. Confirm that the configured workspace and datastore exist.
3. Confirm that one layer exists for every configured variable.
4. Preview a layer using its default style.
5. Verify that changing `sim_time` and `scale` in a WMS request changes the
   selected database time step.

### Check the browser client

Confirm that the map fits the HRU extent, both demonstration variables load,
the legend changes with variable/scale selection, and previous/next controls
change the displayed date.

## Troubleshooting

### `output.hru not found` or `file.cio not found`

Set `task.swat_dir` to the directory containing both files, not to the
`output.hru` file itself.

### `AOI shapefile missing HRU id field`

Check the Shapefile attribute name and set `task.hru_id_field` accordingly.
Column names are normalized to lowercase by the importer.

### HRU row-count or date error

Verify that `file.cio` and `output.hru` came from the same simulation and that
the file layout matches the fixed-width definition implemented by this release.

### Imported geometry does not join to simulation data

Compare the configured Shapefile HRU identifier with the `GIS` values in
`output.hru`. They are joined as text and must represent the same identifiers.

### PostgreSQL permission error

Ask a database administrator to create the PostGIS and `pgcrypto` extensions
and grant the runtime user permission on the target schema and tables, or run
the schema SQL separately and disable automatic initialization.

### GeoServer datastore connection failure

Test the PostgreSQL host and port from the GeoServer host. In containerized
deployments, replace `localhost` with a resolvable service or host name.

### Blank map or failed WMS requests

Check `geoserver.access_url`, browser developer tools, GeoServer logs, the layer
name, requested date, and requested scale. A date without a matching database
record produces no mapped HRU values.

### Basemap does not appear

The satellite and OpenStreetMap layers require internet access. The SWAT WMS
layer can still be displayed over the included blank offline layer.

## Reproducing the SoftwareX case study

The model input files and HRU Shapefile are not bundled in this source tree.
To reproduce the case study, obtain the archived research dataset referenced by
the SoftwareX article, preserve the original filenames, and point the private
runtime YAML file to the extracted locations. If those data cannot be released,
the final repository must state the access restriction and provide a synthetic
or otherwise distributable test dataset that exercises the complete workflow.

For the reported case, the parser read 47,684 `output.hru` rows, removed 364
trailing monthly summary rows, and imported 47,320 valid time-series records
and 364 HRU geometries. Five in-process runs required 28.265 +/- 1.000 s
(mean +/- sample standard deviation) on the hardware and software environment
reported in the article. These values describe the case-study dataset and are
not universal performance guarantees.

## Data, credentials, and publication safety

- Never commit database or GeoServer passwords.
- Do not publish an automatically generated client configuration until its
  service URLs and task metadata have been reviewed.
- Do not publish model inputs unless their license and data-sharing conditions
  permit redistribution.
- Before creating a public release, inspect the complete version-control history
  for credentials; deleting a secret only from the latest revision is
  insufficient. Revoke and rotate any credential that has entered a public or
  shared history.

## Known limitations

- The parser targets the implemented classic SWAT fixed-width `output.hru`
  layout; SWAT+ and arbitrary customized layouts are not supported.
- The supplied browser constructs monthly and yearly timelines but not daily
  timelines.
- Browser labels and palettes are explicitly implemented for `SURQ_GEN` and
  `SYLD`.
- The viewer displays one WMS image layer and does not preload frames,
  double-buffer layers, or interpolate between simulation dates.
- Model calibration, validation, statistical analysis, and causal inference are
  outside the scope of this visualization workflow.

## Citation

If you use SWATVIS in research, cite the associated SoftwareX article and the
archived software release. Replace the placeholders below when the DOI and
repository archive are available:

```text
<Authors> (<Year>). SWATVIS: A Python Toolkit for Interactive Visualization of
SWAT Model Simulations. SoftwareX. <Article DOI>.

<Authors> (<Year>). SWATVIS, version <Version>. <Archive>. <Software DOI>.
```

## Source code availability

The source code associated with the SoftwareX article should be deposited in a
public version-controlled repository and archived in a DOI-issuing repository
such as Zenodo. The manuscript should cite the immutable archived release, while
the development repository may continue to receive updates.

Before submission, replace these placeholders:

- Public repository: `<PUBLIC-REPOSITORY-URL>`
- Archived release: `<ARCHIVE-DOI-OR-URL>`
- Version or commit: `<VERSION-OR-COMMIT>`
- Case-study data: `<DATA-DOI-OR-ACCESS-STATEMENT>`

## License

A public SoftwareX release must include a clear open-source license in a root
`LICENSE` file. No license choice is made by this README because selecting a
license is an author/legal decision. Add the chosen license before public
submission and state it here, for example: `Released under the terms in
LICENSE`.

## Support and contributions

Use the public repository issue tracker to report a reproducible problem. Include
the operating system, Python and dependency versions, SWAT version, `IPRINT`
value, GeoServer/PostgreSQL/PostGIS versions, the command executed, and the full
error message. Remove credentials and private paths before posting logs.
