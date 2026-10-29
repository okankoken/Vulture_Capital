from streamlit.testing.v1 import AppTest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=90).run()
assert not app.exception, app.exception
for market in ["BIST · Türkiye","NASDAQ / NYSE · ABD"]:
    app.sidebar.radio[0].set_value(market).run()
    for page in ["Fırsat radarı","Piyasa radarı","Hisse inceleme","Karşılaştırma","Veri durumu"]:
        app.sidebar.radio[1].set_value(page).run()
        assert not app.exception,(market,page,app.exception)
        print("PASS",market,page,flush=True)
