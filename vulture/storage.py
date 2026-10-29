import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("VULTURE_DATA_DIR", ROOT / "data"))
DB = DATA / "vulture.db"
MARKETS = {"BIST": "Borsa İstanbul", "US": "NASDAQ / NYSE"}


@contextmanager
def connect(readonly=False):
    if readonly:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    else:
        DATA.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB, timeout=60)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=60000")
    try:
        with con:
            yield con
    finally:
        con.close()


def initialize():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS prices (
          market TEXT, symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
          close REAL, adj_close REAL, volume REAL, PRIMARY KEY(market,symbol,date));
        CREATE TABLE IF NOT EXISTS symbols (
          market TEXT, symbol TEXT, name TEXT, currency TEXT, exchange TEXT,
          updated_at TEXT, PRIMARY KEY(market,symbol));
        CREATE TABLE IF NOT EXISTS snapshot (
          market TEXT,symbol TEXT,name TEXT,asof TEXT,last_price REAL,
          r_1d REAL,r_1w REAL,r_1m REAL,r_3m REAL,r_6m REAL,r_1y REAL,
          vol_z REAL,hi_52w REAL,lo_52w REAL,pct_from_hi REAL,
          PRIMARY KEY(market,symbol));
        CREATE TABLE IF NOT EXISTS runs (
          run_date TEXT PRIMARY KEY,status TEXT,started_at TEXT,finished_at TEXT,
          expected INTEGER,succeeded INTEGER,failed INTEGER,source TEXT);
        CREATE TABLE IF NOT EXISTS fetch_log (
          run_date TEXT,market TEXT,symbol TEXT,status TEXT,error TEXT,
          PRIMARY KEY(run_date,market,symbol));
        ''')
