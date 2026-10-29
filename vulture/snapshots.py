"""Portable, consistent SQLite snapshot for an HTTPS object store."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from contextlib import closing
from urllib.parse import urlparse
import requests
from .storage import DB, DATA, ROOT


def export():
    target=ROOT/"runtime"/"publish"
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target) as temporary:
        copy=Path(temporary)/"vulture.db"
        with closing(sqlite3.connect(f"file:{DB}?mode=ro",uri=True)) as src:
            with closing(sqlite3.connect(copy)) as dst:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode=DELETE")
        compressed=Path(temporary)/"vulture.db.gz"
        with copy.open("rb") as source,gzip.open(compressed,"wb",compresslevel=5) as destination:
            shutil.copyfileobj(source,destination)
        digest=hashlib.sha256(compressed.read_bytes()).hexdigest()
        name=f"vulture-{digest[:16]}.db.gz"
        os.replace(compressed,target/name)
        manifest={"file":name,"sha256":digest,"compressed_bytes":(target/name).stat().st_size}
        temporary_manifest=target/"manifest.json.tmp"
        temporary_manifest.write_text(json.dumps(manifest),encoding="utf-8")
        os.replace(temporary_manifest,target/"manifest.json")
        # Only our generated exports; retain two generations to bound disk usage.
        generations=sorted(target.glob("vulture-*.db.gz"),key=lambda p:p.stat().st_mtime,reverse=True)
        for old in generations[2:]:
            old.unlink()
    print(f"Cloud snapshot ready: {name}",flush=True)
    return manifest


def download(manifest_url,token=""):
    """UI reads a published snapshot; never calls the market data provider."""
    if urlparse(manifest_url).scheme!="https":
        raise ValueError("Snapshot manifest must use HTTPS")
    headers={"Authorization":f"Bearer {token}"} if token else {}
    response=requests.get(manifest_url,headers=headers,timeout=30)
    response.raise_for_status()
    manifest=response.json()
    name=manifest["file"]
    if Path(name).name!=name or not name.endswith(".db.gz"):
        raise ValueError("Invalid snapshot filename")
    DATA.mkdir(parents=True,exist_ok=True)
    digest_file=DATA/"snapshot.sha256"
    if DB.exists() and digest_file.exists() and digest_file.read_text()==manifest["sha256"]:
        return
    from urllib.parse import urljoin
    with tempfile.TemporaryDirectory(dir=DATA) as temporary:
        compressed=Path(temporary)/"snapshot.gz"
        digest=hashlib.sha256()
        with requests.get(urljoin(manifest_url,name),headers=headers,stream=True,timeout=(10,180)) as stream:
            stream.raise_for_status()
            total=0
            with compressed.open("wb") as output:
                for chunk in stream.iter_content(1024*1024):
                    total+=len(chunk)
                    if total>512*1024*1024:
                        raise ValueError("Snapshot exceeds 512 MB download limit")
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest()!=manifest["sha256"]:
            raise ValueError("Snapshot checksum mismatch; old snapshot preserved")
        database=Path(temporary)/"vulture.db"
        with gzip.open(compressed,"rb") as source,database.open("wb") as output:
            expanded=0
            while chunk:=source.read(1024*1024):
                expanded+=len(chunk)
                if expanded>2*1024**3:
                    raise ValueError("Expanded snapshot exceeds 2 GB limit")
                output.write(chunk)
        with closing(sqlite3.connect(f"file:{database}?mode=ro",uri=True)) as con:
            if con.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise ValueError("Snapshot database integrity check failed")
            con.execute("SELECT market,symbol FROM snapshot LIMIT 1")
        os.replace(database,DB)
        digest_file.write_text(manifest["sha256"])


if __name__=="__main__":
    export()
