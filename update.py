"""Nightly price update for the Hayridge site.

Runs on GitHub Actions. Downloads 100 days of daily prices for each ticker
from Alpha Vantage (free key, 25 calls a day) and writes prices.json.
The key is read from the AV_KEY secret and never appears on the website.
"""
import datetime
import json
import os
import time
import urllib.parse
import urllib.request

WATCHLIST = ["GLD", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "AMD",
             "INTC", "NFLX", "ORCL", "JPM", "V", "XOM", "LLY", "UNH", "WMT", "T", "VZ"]
KEY = os.environ.get("AV_KEY", "").strip()
OUT = "prices.json"
PAUSE = 13  # seconds between calls, stays inside the free limits


def call(params):
    params = dict(params, apikey=KEY)
    url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.load(r)


def notice(p):
    return p.get("Note") or p.get("Information") or p.get("Error Message") or ""


def main():
    if not KEY:
        raise SystemExit("AV_KEY secret is missing. Add it under Settings > Secrets and variables > Actions.")
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT))
        except Exception:
            old = {}
    series = {s["sym"]: s for s in old.get("series", []) if s.get("sym")}
    movers = old.get("movers")
    out_of_calls = False

    for sym in WATCHLIST:
        for attempt in (1, 2):
            try:
                p = call({"function": "TIME_SERIES_DAILY", "symbol": sym, "outputsize": "compact"})
            except Exception as e:
                print(sym, "request failed:", e)
                p = {}
            ts = p.get("Time Series (Daily)")
            if ts:
                bars = []
                for d in sorted(ts):
                    r = ts[d]
                    bars.append([d, float(r["1. open"]), float(r["2. high"]), float(r["3. low"]),
                                 float(r["4. close"]), int(float(r["5. volume"]))])
                series[sym] = {"sym": sym, "asOf": bars[-1][0], "fetchedAt": int(time.time() * 1000), "bars": bars}
                print(sym, "ok, last close", bars[-1][0])
                break
            msg = notice(p)
            print(sym, "no data:", msg[:160])
            if "per day" in msg and "per second" not in msg:
                out_of_calls = True
                break
            time.sleep(PAUSE * 2)
        if out_of_calls:
            print("Daily call limit reached; keeping yesterday's prices for the rest.")
            break
        time.sleep(PAUSE)

    if not out_of_calls:
        try:
            p = call({"function": "TOP_GAINERS_LOSERS"})

            def pick(rows):
                keep = []
                for r in rows or []:
                    t = r.get("ticker", "")
                    try:
                        px = float(r.get("price", 0))
                    except ValueError:
                        continue
                    if t.isalpha() and t.isupper() and len(t) <= 5 and px >= 3:
                        keep.append({"t": t, "px": px, "r": float(str(r.get("change_percentage", "0")).rstrip("%")) / 100,
                                     "v": int(float(r.get("volume", 0)))})
                return keep[:10]

            if p.get("most_actively_traded"):
                movers = {"asOf": str(p.get("last_updated", ""))[:10], "fetchedAt": int(time.time() * 1000),
                          "active": pick(p.get("most_actively_traded")), "gainers": pick(p.get("top_gainers")),
                          "losers": pick(p.get("top_losers"))}
            else:
                print("movers: no data:", notice(p)[:160])
        except Exception as e:
            print("movers request failed:", e)

    data = {
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "watchlist": WATCHLIST,
        "series": [series[s] for s in WATCHLIST if s in series],
        "movers": movers,
    }
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("wrote", OUT, "with", len(data["series"]), "tickers")


if __name__ == "__main__":
    main()
