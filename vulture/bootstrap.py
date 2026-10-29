"""Import legacy data read-only. Never execute legacy reset scripts."""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .storage import initialize, connect, DATA
from .metrics import write_snapshot


def bootstrap(home):
    initialize()
    for market, folder, filename in [("BIST","StockWizard_AI","symbols_bist100.txt"),
                                      ("US","StockWizard_AI_Nasdaq_NYSE","symbols_us.txt")]:
        source = Path(home) / folder / "data"
        text = (source / filename).read_text(encoding="utf-8-sig")
        (DATA / f"symbols_{market.lower()}.txt").write_text(text, encoding="utf-8")
        old = sqlite3.connect(f"file:{source / 'movers.db'}?mode=ro", uri=True)
        names = {}
        try:
            for row in old.execute("SELECT symbol,short_name,long_name FROM symbols"):
                names[row[0]] = row[2] or row[1] or row[0]
        except sqlite3.OperationalError:
            pass
        with connect() as con:
            symbols = [r[0] for r in old.execute("SELECT DISTINCT symbol FROM prices")]
            for symbol in symbols:
                frame = pd.read_sql_query("SELECT * FROM prices WHERE symbol=? ORDER BY date", old, params=[symbol])
                fields = ["symbol","date","open","high","low","close","adj_close","volume"]
                rows = [(market,*r) for r in frame[fields].itertuples(index=False,name=None)]
                con.executemany("INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?,?,?,?,?)", rows)
                name = names.get(symbol,symbol)
                con.execute("INSERT OR IGNORE INTO symbols VALUES (?,?,?,?,?,?)",
                            (market,symbol,name,"TRY" if market=="BIST" else "USD","",None))
                write_snapshot(con,market,symbol,name,frame)
            print(f"Imported {market}: {len(symbols)} symbols from legacy database",flush=True)
        old.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home",default="/home/train")
    bootstrap(parser.parse_args().home)
