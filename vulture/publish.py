"""Airflow -> public market-data branch; private deploy key stays on the VM."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import tempfile
import pandas as pd
from .storage import ROOT,DB

REMOTE="git@github.com:okankoken/Vulture_Capital.git"
BRANCH="market-data"
WORK=ROOT/"runtime"/"data-publisher"
KEY=ROOT/"runtime"/"publisher_ed25519"


def git(*args):
    env=os.environ.copy()
    known=ROOT/"runtime"/"github_known_hosts"
    env["GIT_SSH_COMMAND"]=f"ssh -i {shlex.quote(str(KEY))} -o UserKnownHostsFile={shlex.quote(str(known))} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes"
    result=subprocess.run(["git",*args],cwd=WORK,env=env,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr[-500:]}")
    return result.stdout.strip()


def prepare():
    WORK.mkdir(parents=True,exist_ok=True)
    if not (WORK/".git").exists():
        git("init","-b",BRANCH)
        git("remote","add","origin",REMOTE)
        git("config","user.name","Vulture Capital Data Pipeline")
        git("config","user.email","132913120+okankoken@users.noreply.github.com")


def export_files():
    """Use SQLite backup so UI exports are internally consistent during ingestion."""
    prepare()
    with tempfile.TemporaryDirectory(dir=ROOT/"runtime") as temporary:
        snapshot=Path(temporary)/"consistent.db"
        with closing(sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=60)) as src:
            with closing(sqlite3.connect(snapshot)) as dst:
                src.backup(dst)
        with closing(sqlite3.connect(snapshot)) as con:
            (WORK/"snapshots").mkdir(exist_ok=True)
            for market in ("BIST","US"):
                frame=pd.read_sql_query('''SELECT s.*,
                    (SELECT p.adj_close FROM prices p WHERE p.market=s.market AND p.symbol=s.symbol
                     AND p.date=s.asof LIMIT 1) AS adj_price
                    FROM snapshot s WHERE s.market=? ORDER BY s.symbol''',con,params=[market])
                frame.to_csv(WORK/"snapshots"/f"{market}.csv",index=False,float_format="%.17g")
                folder=WORK/"history"/market
                folder.mkdir(parents=True,exist_ok=True)
                for symbol in frame.symbol:
                    if not re.fullmatch(r"[A-Z0-9.^=_-]{1,32}",symbol):
                        continue
                    history=pd.read_sql_query("SELECT date,close,adj_close,volume FROM prices WHERE market=? AND symbol=? ORDER BY date",
                                              con,params=[market,symbol])
                    history.to_csv(folder/f"{symbol}.csv",index=False,float_format="%.8g")
                print(f"Exported {market}: {len(frame)} stocks",flush=True)
            pd.read_sql_query("SELECT * FROM runs ORDER BY started_at DESC LIMIT 15",con).to_csv(WORK/"runs.csv",index=False)
            pd.read_sql_query("SELECT run_date,market,symbol,error FROM fetch_log WHERE status='failed' ORDER BY run_date DESC",con).to_csv(WORK/"failures.csv",index=False)
            pd.read_sql_query("SELECT * FROM universe_refresh ORDER BY market",con).to_csv(WORK/"universe_refresh.csv",index=False)
    git("add","snapshots","history","runs.csv","failures.csv","universe_refresh.csv")
    if git("diff","--cached","--name-only"):
        git("commit","-m","Update daily BIST and US market data")
    revision=git("rev-parse","HEAD")
    payload={"data_commit":revision,"exported_at":datetime.now(timezone.utc).isoformat(),"source":"Yahoo Finance / Vulture Capital"}
    (WORK/"manifest.json").write_text(json.dumps(payload),encoding="utf-8")
    git("add","manifest.json")
    if git("diff","--cached","--name-only"):
        git("commit","-m","Publish immutable market data manifest")
    return payload


def publish(export_only=False):
    (ROOT/"runtime").mkdir(exist_ok=True)
    with (ROOT/"runtime"/"publish.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        payload=export_files()
        if not export_only:
            if not KEY.exists():
                raise RuntimeError("Publisher deploy key has not been configured")
            # Normal push only; never force-push another writer's work.
            git("push","origin",f"HEAD:refs/heads/{BRANCH}")
        print(json.dumps(payload),flush=True)
        return payload


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--export-only",action="store_true")
    publish(parser.parse_args().export_only)
