import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from vulture.metrics import summarize, dip_distance


class MetricsTest(unittest.TestCase):
    def test_low_distance_uses_actual_price_after_extreme_drawdown(self):
        frame=pd.DataFrame({"hi_52w":[300000.],"pct_from_hi":[-.999999997],
                            "adj_price":[.001],"lo_52w":[.001]})
        self.assertEqual(dip_distance(frame).iloc[0],0.)

    def test_split_uses_adjusted_return_but_raw_display_price(self):
        frame=pd.DataFrame({"date":["2026-01-01","2026-01-02"],"close":[100.,51.],
                            "adj_close":[50.,51.],"volume":[10.,20.]})
        result=summarize(frame)
        self.assertAlmostEqual(result["r_1d"],.02)
        self.assertEqual(result["last_price"],51.)
        self.assertIsNone(result["r_1y"])

    def test_monthly_return_uses_prior_available_session(self):
        frame=pd.DataFrame({"date":["2026-01-29","2026-01-30","2026-03-01"],
                            "close":[90.,100.,120.],"adj_close":[90.,100.,120.],"volume":[10.,10.,10.]})
        self.assertAlmostEqual(summarize(frame)["r_1m"],.2)
        self.assertIsNone(summarize(frame)["vol_z"])

    def test_empty_history(self):
        frame=pd.DataFrame(columns=["date","close","adj_close","volume"])
        self.assertIsNone(summarize(frame))


class PipelineTest(unittest.TestCase):
    def test_failed_symbol_keeps_existing_prices_and_retry_skips_successes(self):
        from vulture import storage, pipeline
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(storage,"DATA",root),patch.object(storage,"DB",root/"vulture.db"),patch.object(pipeline,"DATA",root):
                storage.initialize()
                (root/"symbols_bist.txt").write_text("AAA.IS\n")
                (root/"symbols_us.txt").write_text("BBB\n")
                with storage.connect() as con:
                    con.execute("INSERT INTO prices VALUES ('US','BBB','2025-01-01',1,1,1,1,1,1)")
                frame=pd.DataFrame({"symbol":["AAA.IS","AAA.IS"],"date":["2026-01-01","2026-01-02"],
                    "open":[1.,2.],"high":[1.,2.],"low":[1.,2.],"close":[1.,2.],"adj_close":[1.,2.],"volume":[10.,20.]})
                def first(symbol):
                    if symbol=="BBB":
                        raise ValueError("provider unavailable")
                    return frame,{}
                with patch.object(pipeline,"fetch",side_effect=first):
                    with self.assertRaises(RuntimeError):
                        pipeline.run()
                with storage.connect() as con:
                    self.assertEqual(con.execute("SELECT close FROM prices WHERE symbol='BBB'").fetchone()[0],1)
                    self.assertEqual(con.execute("SELECT status FROM runs").fetchone()[0],"partial")
                updated=frame.copy()
                updated["symbol"]="BBB"
                with patch.object(pipeline,"fetch",return_value=(updated,{})) as fetch:
                    pipeline.run()
                    fetch.assert_called_once_with("BBB")
                with patch.object(pipeline,"fetch") as fetch:
                    pipeline.run()
                    fetch.assert_not_called()
                # A new listing discovered after today's success must still be fetched.
                (root/"symbols_us.txt").write_text("BBB\nCCC\n")
                updated["symbol"]="CCC"
                with patch.object(pipeline,"fetch",return_value=(updated,{})) as fetch:
                    pipeline.run()
                    fetch.assert_called_once_with("CCC")


if __name__=="__main__":
    unittest.main()
