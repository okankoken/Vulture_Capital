"""Read public market exports at one immutable Git commit, without credentials."""
from io import StringIO
import re
from urllib.parse import quote
import pandas as pd
import requests

REPOSITORY = "okankoken/Vulture_Capital"
BASE = f"https://raw.githubusercontent.com/{REPOSITORY}"


def manifest():
    response=requests.get(f"{BASE}/market-data/manifest.json",timeout=(8,20))
    response.raise_for_status()
    value=response.json()
    if not re.fullmatch(r"[a-f0-9]{40}",value.get("data_commit","")):
        raise ValueError("Invalid published data revision")
    return value


def read_csv(revision,path):
    if not re.fullmatch(r"[a-f0-9]{40}",revision):
        raise ValueError("Invalid revision")
    response=requests.get(f"{BASE}/{revision}/{path}",timeout=(8,30))
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text),keep_default_na=False,na_values=[""])


def query(sql,params,revision):
    if sql.startswith("SELECT * FROM snapshot"):
        market=params[0]
        if market not in ("BIST","US"):
            raise ValueError("Invalid market")
        frame=read_csv(revision,f"snapshots/{market}.csv")
        # A legitimate US ticker 'NA' must remain a string, not a missing value.
        return frame
    if sql.startswith("SELECT date,close,adj_close,volume FROM prices"):
        market,symbol=params
        if market not in ("BIST","US") or not re.fullmatch(r"[A-Z0-9.^=_-]{1,32}",symbol):
            raise ValueError("Invalid symbol")
        return read_csv(revision,f"history/{market}/{quote(symbol,safe='')}.csv")
    if sql.startswith("SELECT * FROM runs"):
        return read_csv(revision,"runs.csv")
    if sql.startswith("SELECT * FROM universe_refresh"):
        return read_csv(revision,"universe_refresh.csv")
    if sql.startswith("SELECT market,symbol,error FROM fetch_log"):
        frame=read_csv(revision,"failures.csv")
        return frame.loc[frame.run_date==params[0],["market","symbol","error"]]
    raise ValueError("Unsupported published-data query")
