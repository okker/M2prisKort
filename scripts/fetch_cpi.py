"""Henter forbrugerprisindekset (FPI) fra Danmarks Statistik og laver en kvartalsserie.

Danmarks Statistik lagde FPI-tabellerne om i 2026:
  PRIS01  – ny tabel, 2000M12 og frem (varegruppe 000000 = FPI i alt)
  PRIS113 – gammel tabel, 1980M01–2025M12, lukket for nye tal

Serierne kædes sammen: PRIS01 bruges hvor den findes, og PRIS113 skaleres til
PRIS01's niveau med det gennemsnitlige forhold i overlappet (forholdet er
konstant bortset fra afrunding). Kvartalstal = gennemsnit af månederne.

Output: data/raw/fpi_kvartal.csv med kolonnerne kvartal,fpi (kun hele kvartaler)
"""

import csv
import io
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

API = "https://api.statbank.dk/v1/data"
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / "fpi_kvartal.csv"


def fetch(table, variables):
    body = json.dumps({"table": table, "format": "CSV", "lang": "da", "variables": variables}).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8-sig")
    return {
        row["TID"]: float(row["INDHOLD"].replace(",", "."))
        for row in csv.DictReader(io.StringIO(text), delimiter=";")
        if row["INDHOLD"] not in ("", "..")
    }


def main():
    new = fetch("PRIS01", [
        {"code": "VAREGR", "values": ["000000"]},
        {"code": "ENHED", "values": ["100"]},
        {"code": "Tid", "values": ["*"]},
    ])
    old = fetch("PRIS113", [{"code": "TYPE", "values": ["INDEKS"]}, {"code": "Tid", "values": ["*"]}])

    overlap = sorted(set(new) & set(old))
    factor = sum(new[m] / old[m] for m in overlap) / len(overlap)
    monthly = {m: v * factor for m, v in old.items()}
    monthly.update(new)
    print(f"PRIS113 → PRIS01: faktor {factor:.5f} ud fra {len(overlap)} overlappende måneder")

    by_quarter = defaultdict(list)
    for m, v in monthly.items():
        year, month = int(m[:4]), int(m[5:])
        by_quarter[f"{year}K{(month - 1) // 3 + 1}"].append(v)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["kvartal", "fpi"])
        for q in sorted(by_quarter):
            if len(by_quarter[q]) == 3:  # kun hele kvartaler
                w.writerow([q, round(sum(by_quarter[q]) / 3, 3)])
    last = max(monthly)
    print(f"Skrev {len(by_quarter)} kvartaler til {OUT} (seneste måned: {last})")


if __name__ == "__main__":
    main()
