import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from vulture import symbols,storage,pipeline
from vulture.metrics import summarize


class DirectoryTest(unittest.TestCase):
    def test_kap_next_payload_and_multi_codes(self):
        payload='22:{"stockCode":"NEWCO"},{"stockCode":"THYAO, AKBNK"},{"stockCode":"TOOLONG"}'
        html='<script>self.__next_f.push('+json.dumps([1,payload])+')</script>'
        self.assertEqual(symbols.parse_bist(html),{"NEWCO.IS","THYAO.IS","AKBNK.IS"})

    def test_official_us_filters_and_share_class_translation(self):
        text="ACT Symbol|Security Name|Exchange|ETF|Test Issue\nBRK.B|Berkshire Class B Common Stock|N|N|N\nETF1|Example ETF|N|Y|N\nTEST|Test Stock|N|N|Y\nABC.W|Example Warrants|N|N|N\nOTHER|Other Exchange Common Stock|P|N|N\nNA|Example Common Stock|N|N|N\nFile Creation Time: 1029202612:00||||\n"
        self.assertEqual(symbols.parse_us(text,other=True),{"BRK-B","NA"})

    def test_failed_market_preserves_file_and_success_adds_without_removing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(storage,"DATA",root),patch.object(storage,"DB",root/"vulture.db"),patch.object(symbols,"DATA",root):
                (root/"symbols_bist.txt").write_text("OLDX.IS\n")
                (root/"symbols_us.txt").write_text("OLDUS\n")
                fetched={f"S{i:04d}.IS" for i in range(300)}
                def broken():
                    raise RuntimeError("network unavailable")
                result=symbols.refresh_all({"BIST":lambda:fetched,"US":broken})
                self.assertEqual(result[0]["added"],300)
                self.assertIn("OLDX.IS",symbols.existing("BIST"))
                self.assertEqual((root/"symbols_us.txt").read_text(),"OLDUS\n")
                self.assertEqual(result[1]["status"],"failed")
                again=symbols.refresh_all({"BIST":lambda:fetched,"US":broken})
                self.assertEqual(again[0]["added"],0)

    def test_suspiciously_small_directory_is_not_written(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(storage,"DATA",root),patch.object(storage,"DB",root/"vulture.db"),patch.object(symbols,"DATA",root):
                path=root/"symbols_bist.txt"
                path.write_text("KEEP.IS\n")
                result=symbols.refresh_all({"BIST":lambda:{"NEW.IS"},"US":lambda:set()})
                self.assertEqual(path.read_text(),"KEEP.IS\n")
                self.assertEqual(result[0]["status"],"failed")

    def test_first_trading_day_is_accepted_with_no_invented_returns(self):
        response=Mock()
        response.status_code=200
        response.json.return_value={"chart":{"result":[{"timestamp":[1793232000],
            "indicators":{"quote":[{"open":[10],"high":[11],"low":[9],"close":[10],"volume":[100]}]},"meta":{}}]}}
        with patch.object(pipeline.requests,"get",return_value=response):
            frame,_=pipeline.fetch("NEWCO.IS")
        self.assertEqual(len(frame),1)
        stats=summarize(frame)
        self.assertEqual(stats["last_price"],10)
        self.assertIsNone(stats["r_1d"])
        self.assertIsNone(stats["r_1y"])


if __name__=="__main__":
    unittest.main()
