"""Discover new listings from KAP and Nasdaq Trader; never shrink existing lists."""
import csv
import fcntl
from html.parser import HTMLParser
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
import requests
from .storage import DATA, initialize, connect

KAP_URL="https://www.kap.org.tr/tr/bist-sirketler"
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NYSE_URL="https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside=False
        self.current=[]
        self.scripts=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script":
            self.inside=True
            self.current=[]
    def handle_data(self,value):
        if self.inside:
            self.current.append(value)
    def handle_endtag(self,tag):
        if tag=="script" and self.inside:
            self.scripts.append("".join(self.current))
            self.inside=False


def parse_bist(html):
    parser=Scripts()
    parser.feed(html)
    payloads=[html]
    marker="self.__next_f.push("
    for script in parser.scripts:
        start=script.find(marker)
        if start<0:
            continue
        try:
            payload=json.loads(script[start+len(marker):script.rfind(")")])
            payloads.extend(value for value in payload if isinstance(value,str))
        except (ValueError,TypeError):
            continue
    symbols=set()
    for payload in payloads:
        for value in re.findall(r'"stockCode"\s*:\s*"([^"\\]*)"',payload):
            for code in re.split(r"[,;\s]+",value.upper()):
                if re.fullmatch(r"[A-Z0-9]{4,5}",code):
                    symbols.add(code+".IS")
    return symbols


NON_EQUITY=re.compile(r"\b(warrants?|rights?|units?|preferred|debentures?|bonds?|notes?)\b",re.I)


def parse_us(text,other=False):
    reader=csv.DictReader(StringIO(text),delimiter="|")
    required={"Security Name","Test Issue","ETF", "ACT Symbol" if other else "Symbol"}
    if other:
        required.add("Exchange")
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Unexpected Nasdaq directory columns")
    symbols=set()
    for row in reader:
        if row.get("Test Issue")!="N" or row.get("ETF")!="N":
            continue
        if other and row.get("Exchange")!="N":
            continue
        if NON_EQUITY.search(row.get("Security Name") or ""):
            continue
        raw=(row.get("ACT Symbol" if other else "Symbol") or "").strip().upper()
        # Yahoo represents NYSE share classes as BRK-B, not BRK.B.
        symbol=raw.replace(".","-")
        if re.fullmatch(r"[A-Z][A-Z0-9]{0,6}(?:-[A-Z0-9]{1,2})?",symbol):
            symbols.add(symbol)
    return symbols


def get_text(url):
    response=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=(10,30))
    response.raise_for_status()
    return response.text


def fetch_bist():
    return parse_bist(get_text(KAP_URL))


def fetch_us():
    # Both official directories must succeed before changing the US list.
    return parse_us(get_text(NASDAQ_URL)) | parse_us(get_text(NYSE_URL),other=True)


def existing(market):
    path=DATA/f"symbols_{market.lower()}.txt"
    if not path.exists():
        return set()
    codes={line.strip().upper() for line in path.read_text(encoding="utf-8-sig").splitlines()
           if line.strip() and not line.lstrip().startswith("#")}
    return {code if market=="US" or code.endswith(".IS") else code+".IS" for code in codes}


def atomic_list(path,symbols):
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,
                                     prefix=path.name+".",suffix=".tmp",delete=False) as output:
        temporary=Path(output.name)
        output.write("\n".join(sorted(symbols))+"\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary,path)


def refresh_all(fetchers=None):
    initialize()
    fetchers=fetchers or {"BIST":fetch_bist,"US":fetch_us}
    results=[]
    with (DATA/"universe.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for market in ("BIST","US"):
            previous=existing(market)
            now=datetime.now(timezone.utc).isoformat()
            source=KAP_URL if market=="BIST" else NASDAQ_URL+" ; "+NYSE_URL
            try:
                discovered=set(fetchers[market]())
                minimum=300 if market=="BIST" else 2000
                maximum=3000 if market=="BIST" else 25000
                if not minimum<=len(discovered)<=maximum:
                    raise ValueError(f"Suspicious directory size: {len(discovered)}")
                added=sorted(discovered-previous)
                combined=previous|discovered
                atomic_list(DATA/f"symbols_{market.lower()}.txt",combined)
                row=(market,now,"success",len(discovered),len(added),len(combined),json.dumps(added),source,None)
            except Exception as exc:
                row=(market,now,"failed",0,0,len(previous),"[]",source,str(exc)[:250])
            with connect() as con:
                con.execute("INSERT OR REPLACE INTO universe_refresh VALUES (?,?,?,?,?,?,?,?,?)",row)
            result=dict(zip(["market","checked_at","status","discovered","added","total","new_symbols","source","error"],row))
            results.append(result)
            summary={key:value for key,value in result.items() if key!="new_symbols"}
            summary["sample_new_symbols"]=json.loads(result["new_symbols"])[:10]
            print(json.dumps(summary,ensure_ascii=False),flush=True)
    return results


if __name__=="__main__":
    refresh_all()
