import numpy as np
import pandas as pd


def summarize(frame):
    """Adjusted total returns; raw latest close is displayed as the price."""
    x = frame.sort_values("date").copy()
    x["date"] = pd.to_datetime(x["date"])
    x = x.dropna(subset=["close", "adj_close"])
    if x.empty:
        return None
    last = x.iloc[-1]
    adjusted = x["adj_close"]
    result = {"asof": last["date"].date().isoformat(), "last_price": float(last["close"])}
    for label, bars in [("r_1d", 1), ("r_1w", 5)]:
        base = adjusted.iloc[-bars-1] if len(x) > bars else None
        result[label] = float(adjusted.iloc[-1] / base - 1) if base and base > 0 else None
    for label, months in [("r_1m",1),("r_3m",3),("r_6m",6),("r_1y",12)]:
        past = x[x.date <= last.date - pd.DateOffset(months=months)]
        base = past.adj_close.iloc[-1] if len(past) else None
        result[label] = float(adjusted.iloc[-1] / base - 1) if base and base > 0 else None
    vol = x.volume.tail(30)
    std = vol.std()
    result["vol_z"] = float((vol.iloc[-1] - vol.mean()) / std) if len(vol) > 1 and std > 0 else None
    year = x[x.date >= last.date - pd.DateOffset(years=1)].adj_close
    result.update(hi_52w=float(year.max()), lo_52w=float(year.min()),
                  pct_from_hi=float(adjusted.iloc[-1] / year.max() - 1) if year.max() > 0 else None)
    return {k: None if isinstance(v, (float,np.floating)) and not np.isfinite(v) else v for k,v in result.items()}


def write_snapshot(con, market, symbol, name, frame):
    result = summarize(frame)
    if result:
        row = {"market":market,"symbol":symbol,"name":name,**result}
        columns = ",".join(row)
        placeholders = ",".join("?" for _ in row)
        con.execute(f"INSERT OR REPLACE INTO snapshot ({columns}) VALUES ({placeholders})", list(row.values()))
