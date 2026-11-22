# SWATVIS

SWATVIS publishes HRU-level SWAT2012 results as dated WMS maps. This release targets the fixed-width output layout in the bundled Yanjiga example (SWAT2012 Rev 591). Check other writers against the regression test before using their outputs. SWAT+ uses different files.

## Choose your user path

**Viewing a published site.** Open the URL supplied by the publisher. Choose SYLD (sediment yield, t/ha) or SURQ_GEN (surface runoff, mm), select Monthly or Yearly, and move the timeline. Select the ⇆ button for two dates with a shared map extent and legend. The globe switches among a plain background, OpenStreetMap and satellite imagery. The date on an annual map represents the full year.

**Publishing a simulation.** The initial setup requires a working Python environment, a spatial database, and a map server. A database or server administrator may need to help with installation, privileges, network access, and hosting. Once these services are ready, each new task uses a configuration file and one publication command.

### Path to the first map

1. Download [V1.0](https://github.com/JinfengM/SWATVIS/releases/tag/V1.0) and unpack it. From the repository root, extract `example/output.rar` into `example/` using a RAR-capable extractor. The resulting `output.hru` must be beside `file.cio`. The polygon shapefile and its sidecars are in `example/geometry/`.
2. In a terminal, change directory to `src`. Run `conda env create -f environment.yml`, followed by `conda activate swat-postproc-env`. The supplied environment pins Python 3.10.18. The revision benchmark used Python 3.12.11.
3. Prepare a PostgreSQL database with PostGIS and pgcrypto available. The schema is `src/sql/swat_vector_time_schema.sql`. An administrator can apply it to the target database and grant the publisher access to the two tables. Set `initialize_schema: false` if it is managed separately.
4. Start GeoServer with the PostGIS datastore available. Its host must reach the database. The publishing account needs permission to create the workspace, datastore, SQL Views and styles.
5. Copy `swat_vector_time_config.example.yaml` to `swat_vector_time_config.yaml` in `src`. Edit only the private copy. Set database and GeoServer connections, public-facing GeoServer URL and task name. The sample paths resolve when commands run in `src`. Keep the HRU GIS identifiers as text, including leading zeros.
6. Run `python swat_vector_time_pipeline.py -c swat_vector_time_config.yaml`. The publisher checks the geometry/record identifiers and coverage before replacing the task rows. It writes both tables in one transaction. Review any error before rerunning. Reusing a task name replaces its previous results.
7. Check the log for **364 polygons, 130 complete time steps, and 47,320 records**. The two example layers each have a monthly and an annual style. The generated `result_display/geoserver_config.js` contains endpoints, dates, class limits and colours.
8. From `src`, run `python -m http.server 8000 --bind 127.0.0.1 --directory result_display`, then open `http://127.0.0.1:8000/`. For a public site, serve that directory with a web server and use a GeoServer URL reachable from the audience's browsers.
9. Select **SYLD → Yearly → ⇆**. Move the two sliders to 2012 and 2015. Use the same legend for both dates. To identify the HRU associated with a stored value, query the published SQL View (GIS field) or the PostGIS tables.

## Configuration and data checks

- The annotations in `src/swat_vector_time_config.example.yaml` describe each setting. The database is initialized from `src/sql/`. `--skip-import` reuses previously imported data. `--skip-geoserver` runs the import alone. `--display-config PATH` sets the output location.
- The case contains 43,680 monthly records and 3,640 annual summaries after a one-year warm-up. The final block has one average annual summary per HRU, marked `10.0`. The importer checks the marker and the set of identifiers before excluding this block. The browser supports monthly and annual data.
- Set `publish.class_bins` to the maximum number of classes. For the example's nonnegative variables, zero receives its own class when present and more than one class is requested. Positive quantiles use observed upper bounds. Duplicate bounds collapse. `equal_interval` is also available. `publish.colors` accepts an ordered list of six-digit hexadecimal colours from low to high. The server and client use the same colours. Publishing another numeric column also requires adding a selector option and label in the supplied client.
- After extracting the example, run `python -m unittest discover -s ../tests` from `src`. The regression checks read both full-width fields from every source row, exercise wider identifiers, invalid input, daily warm-up dates, and verify that all example classes contain observations.
- For a source-to-map check, match GIS, scale, and date. For example, line 14052 (one-based, including nine header lines) has GIS 000170011 and annual SYLD 205.246 for 2011. Query `swat_hru_timeseries` using this GIS, `iprint=2`, and `sim_time='2011-01-01'`. Request the SYLD layer with `viewparams=sim_time:2011-01-01;scale:yearly` and its yearly style. Each positive interval excludes its lower bound and includes its upper bound.

## Reproducing the published example

From `src`, run `python ../tests/verify_publication.py -c swat_vector_time_config.yaml` after publication. This read-only example check queries three reported source lines, the PostGIS table, the GeoServer SQL View over WFS, and the rendered WMS colour inside each HRU. It also prints every GIS identifier classified in the highest annual SYLD class at both selected dates. It requires Pillow for decoding PNG images (`python -m pip install Pillow` if needed).

## License and source

Apache License 2.0. See [LICENSE](LICENSE). The source and example are distributed together in [the V1.0 release](https://github.com/JinfengM/SWATVIS/releases/tag/V1.0).
