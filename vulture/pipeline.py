"""One scheduled run per Istanbul calendar date; resumable per-symbol fetches."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import fcntl
import json
import logging
import os
import time
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from .storage import DATA, initialize, connect
from .metrics import write_snapshot

LOG = logging.getLogger(__name__)


class UnavailableSymbol(ValueError):
    """Permanent provider response: preserve old data, skip immediate retries."""


def universe():
    result = []
    for market in ("BIST", "US"):
        lines = (DATA / f"symbols_{market.lower()}.txt").read_text(encoding="utf-8-sig").splitlines()
        for raw in sorted(set(line.strip().upper() for line in lines if line.strip() and not line.startswith("#"))):
            symbol = raw if market == "US" or raw.endswith(".IS") else raw + ".IS"
            result.append((market,symbol))
    return sorted(set(result))


def fetch(symbol):
    # Re-fetch two years to reconcile split/dividend adjustments, without deleting history.
    end = datetime.now(timezone.utc)
    params = {"period1":int((end-timedelta(days=800)).timestamp()),"period2":int(end.timestamp()),
              "interval":"1d","events":"div,split"}
    for attempt in range(3):
        try:
            response = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                                    params=params,headers={"User-Agent":"Mozilla/5.0"},timeout=(10,35))
            if response.status_code == 404:
                raise UnavailableSymbol("Symbol unavailable from provider")
            response.raise_for_status()
            chart = response.json()["chart"]
            if chart.get("error") or not chart.get("result"):
                raise UnavailableSymbol("Provider returned no chart")
            data = chart["result"][0]
            quotes = data["indicators"]["quote"][0]
            timestamps = data.get("timestamp",[])
            adjusted = (data["indicators"].get("adjclose") or [{}])[0].get("adjclose")
            rows = []
            for i, stamp in enumerate(timestamps):
                close = quotes["close"][i]
                if close is None or close <= 0:
                    continue
                adj = adjusted[i] if adjusted and adjusted[i] is not None else close
                rows.append((symbol,datetime.fromtimestamp(stamp,timezone.utc).date().isoformat(),
                             quotes["open"][i],quotes["high"][i],quotes["low"][i],close,adj,quotes["volume"][i]))
            if not rows:
                raise UnavailableSymbol("No valid price bars")
            frame = pd.DataFrame(rows,columns=["symbol","date","open","high","low","close","adj_close","volume"])
            return frame,data.get("meta",{})
        except UnavailableSymbol:
            raise
        except (requests.RequestException,KeyError,ValueError,IndexError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt+1))


def run(limit=None,new_only=False):
    initialize()
    with open(DATA / "daily.lock","a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another daily update is already running")
        return _run_locked(limit,new_only)


def _run_locked(limit=None,new_only=False):
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()
    if limit:
        today += "-smoke"  # Smoke checks must never mark a full daily run complete.
    targets = universe()
    if new_only:
        today += "-new-listings"
        with connect(readonly=True) as con:
            targets=[(market,symbol) for market,encoded in con.execute(
                "SELECT market,new_symbols FROM universe_refresh WHERE status='success'")
                for symbol in json.loads(encoded)]
        if not targets:
            print("No newly discovered symbols to fetch",flush=True)
            return
    if limit:
        targets = [x for m in ("BIST","US") for x in [r for r in targets if r[0]==m][:limit]]
    if not targets:
        raise RuntimeError("Empty symbol universe")
    with connect() as con:
        previous = con.execute("SELECT status FROM runs WHERE run_date=?",(today,)).fetchone()
        done = set(con.execute("SELECT market,symbol FROM fetch_log WHERE run_date=? AND status='success'",(today,)))
        if previous and previous[0] == "success" and set(targets).issubset(done):
            print("Already completed this calendar date; skipped",flush=True)
            return
        started = datetime.now(timezone.utc).isoformat()
        con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(run_date) DO UPDATE SET status='running',finished_at=NULL,expected=excluded.expected",
                    (today,"running",started,None,len(targets),len(done),0,"Yahoo Finance"))
    def worker(item):
        time.sleep(.15)
        return fetch(item[1])
    pending = [item for item in targets if item not in done]
    failed = 0
    transient_failures = 0
    with ThreadPoolExecutor(max_workers=int(os.environ.get("VULTURE_FETCH_WORKERS","8"))) as pool:
        jobs = {pool.submit(worker,item):item for item in pending}
        for future in as_completed(jobs):
            market,symbol = jobs[future]
            try:
                frame,meta = future.result()
                now = datetime.now(timezone.utc).isoformat()
                name = meta.get("longName") or meta.get("shortName") or symbol
                with connect() as con:
                    con.executemany('''INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(market,symbol,date) DO UPDATE SET open=excluded.open,high=excluded.high,
                      low=excluded.low,close=excluded.close,adj_close=excluded.adj_close,volume=excluded.volume''',
                      [(market,*row) for row in frame.itertuples(index=False,name=None)])
                    con.execute("INSERT OR REPLACE INTO symbols VALUES (?,?,?,?,?,?)",
                                (market,symbol,name,meta.get("currency"),meta.get("exchangeName"),now))
                    write_snapshot(con,market,symbol,name,frame)
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?)",(today,market,symbol,"success",None))
                done.add((market,symbol))
            except Exception as exc:
                failed += 1
                if not isinstance(exc,UnavailableSymbol):
                    transient_failures += 1
                with connect() as con:
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?)",
                                (today,market,symbol,"failed",str(exc)[:200]))
                LOG.warning("Fetch failed %s %s: %s",market,symbol,exc)
            if (len(done)+failed)%100==0:
                print(f"Progress: {len(done)} succeeded / {failed} failed",flush=True)
            with connect() as con:
                con.execute("UPDATE runs SET succeeded=?,failed=? WHERE run_date=?",(len(done),failed,today))
    status = "success" if failed==0 else "partial"
    with connect() as con:
        con.execute("UPDATE runs SET status=?,finished_at=? WHERE run_date=?",
                    (status,datetime.now(timezone.utc).isoformat(),today))
    print(json.dumps({"status":status,"succeeded":len(done),"failed":failed}),flush=True)
    if transient_failures:
        raise RuntimeError(f"{transient_failures} transient failures ({failed} unavailable/failed total); prior data preserved. Retry resumes failures only.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,help="Smoke-test symbols per market, not a full update")
    p.add_argument("--new-only",action="store_true",help="Fetch only symbols found by the latest directory refresh")
    args=p.parse_args()
    run(args.limit,args.new_only)
