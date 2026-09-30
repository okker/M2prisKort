"""Henter disponibel familieindkomst pr. kommune fra Danmarks Statistik (tabel INDKF132).

Vi bruger gennemsnittet for par (FAMTYP=PAIA), ikke alle familier: typiske boligkøbere er
par, og København har mange enlige, som ellers ville trække gennemsnittet kunstigt ned
(2024: 418.000 kr. for alle familier mod 730.000 kr. for par).

Output: data/raw/indkomst_kommuner.csv med kolonnerne omraade_kode,aar,kr (nominelle kroner)
"""

import csv
import io
import json
import urllib.request
from pathlib import Path

API = "https://api.statbank.dk/v1/data"
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "indkomst_kommuner.csv"


def main():
    body = json.dumps({
        "table": "INDKF132", "format": "CSV", "lang": "da", "valuePresentation": "Code",
        "variables": [
            {"code": "OMRÅDE", "values": ["*"]},
            {"code": "ENHED", "values": ["117"]},      # gennemsnit pr. familie (kr.)
            {"code": "FAMTYP", "values": ["PAIA"]},    # par i alt
            {"code": "INDKINTB", "values": ["99"]},    # alle indkomstintervaller
            {"code": "Tid", "values": ["*"]},
        ],
    }).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8-sig")), delimiter=";"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["omraade_kode", "aar", "kr"])
        for r in rows:
            if r["INDHOLD"] not in ("", ".."):
                w.writerow([int(r["OMRÅDE"]), r["TID"], r["INDHOLD"]])
    years = sorted({r["TID"] for r in rows})
    print(f"Skrev {len(rows)} rækker ({len({r['OMRÅDE'] for r in rows})} områder, {years[0]}–{years[-1]}) til {OUT}")


if __name__ == "__main__":
    main()
