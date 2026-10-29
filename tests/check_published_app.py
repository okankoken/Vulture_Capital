"""Exercise the real exports through the Cloud adapter, with no market API calls."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from vulture import github_data
os.environ["VULTURE_USE_PUBLISHED_DATA"]="1"


def local_csv(revision,path):
    return pd.read_csv(root/"runtime"/"data-publisher"/path,keep_default_na=False,na_values=[""])


with patch.object(github_data,"manifest",return_value={"data_commit":"0"*40}),patch.object(github_data,"read_csv",side_effect=local_csv):
    app=AppTest.from_file(str(root/"app.py"),default_timeout=90).run()
    assert not app.exception,app.exception
    for market in ["BIST · Türkiye","NASDAQ / NYSE · ABD"]:
        app.sidebar.radio[0].set_value(market).run()
        for page in ["Fırsat radarı","Piyasa radarı","Hisse inceleme","Karşılaştırma","Veri durumu"]:
            app.sidebar.radio[1].set_value(page).run()
            assert not app.exception,(market,page,app.exception)
            print("PASS PUBLISHED",market,page,flush=True)
