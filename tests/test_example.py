"""Regression checks using the bundled Rev 591 output.hru (extract output.rar first)."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import swat_vector_time_pipeline as pipeline


class ExampleRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "example"
        cls.source = cls.directory / "output.hru"
        cls.rows = cls.source.read_text().splitlines()[9:]
        cls.frame = pipeline.read_hru_strict_frame(cls.source)

    def test_full_width_values(self):
        self.assertEqual(len(self.rows), 47684)
        for field, start, end in [("surq_gen", 204, 214), ("syld", 324, 334)]:
            expected = np.array([float(row[start:end]) for row in self.rows])
            np.testing.assert_array_equal(self.frame[field].astype(float), expected)

    def test_large_identifiers(self):
        row = "PAST12345 0000100071234512345" + self.rows[0][29:]
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "output.hru"
            sample.write_text("\n" * 9 + row + "\n")
            rec = pipeline.read_hru_strict_frame(sample).iloc[0]
        self.assertEqual(
            (rec.hru, rec.gis, rec["sub"], rec.mgt),
            ("12345", "000010007", "12345", "12345"),
        )

    def test_summary_block(self):
        clean = pipeline.strip_run_summary(self.frame, self.directory / "file.cio")
        self.assertEqual(len(clean), 47320)
        self.assertEqual(
            len(pipeline.strip_run_summary(clean, self.directory / "file.cio")),
            len(clean),
        )
        bad = self.frame.copy()
        bad.loc[bad.index[-1], "mon"] = "9.0"
        with self.assertRaises(ValueError):
            pipeline.strip_run_summary(bad, self.directory / "file.cio")

    def test_daily_calendar(self):
        data = pd.DataFrame({"hru": [1, 1, 1], "mon": [1, 2, 3]})
        dates = pipeline.add_time_columns(data, 1, self.directory / "file.cio")
        self.assertEqual(
            list(map(str, dates.sim_time)), ["2009-01-01", "2009-01-02", "2009-01-03"]
        )

    def test_mapping_failures(self):
        gdf, field, *_ = pipeline.read_aoi_frame(
            {"task": {"aoi_shapefile": self.directory / "geometry" / "fullhru.shp"}}
        )
        frame = pipeline.parse_hru_output(self.directory)
        self.assertEqual(
            pipeline.validate_hru_mapping(gdf, field, frame)["time_steps"], 130
        )
        with self.assertRaises(ValueError):
            pipeline.validate_hru_mapping(pd.concat([gdf, gdf.iloc[:1]]), field, frame)
        empty = gdf.copy()
        empty.loc[empty.index[0], "geometry"] = None
        with self.assertRaises(ValueError):
            pipeline.validate_hru_mapping(empty, field, frame)
        damaged = frame.copy()
        damaged.iloc[1] = damaged.iloc[0]
        with self.assertRaises(ValueError):
            pipeline.validate_hru_mapping(gdf, field, damaged)

    def test_occupied_classes(self):
        for field in ("syld", "surq_gen"):
            for group in (
                self.frame[self.frame.mon.str.len() == 4],
                self.frame[self.frame.mon.isin(map(str, range(1, 13)))],
            ):
                values = group[field].astype(float)
                levels = pipeline.compute_levels(values, 10, "quantile")
                self.assertEqual(levels[0], 0)
                self.assertEqual(
                    len(np.unique(np.searchsorted(levels, values))), len(levels)
                )
                self.assertEqual(levels[-1], values.max())


if __name__ == "__main__":
    unittest.main()
