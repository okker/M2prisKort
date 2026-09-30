"""Henter data fra Boligmarkedsstatistikken.

  BM010 – m²-pris pr. kommune              → data/raw/bm010_kommuner.csv
  BM011 – m²-pris pr. postnummer           → data/raw/bm011_postnumre.csv
  BM020 – antal solgte pr. kommune (2004-)  → data/raw/bm020_kommuner.csv
  BM021 – antal solgte pr. postnummer (2004-) → data/raw/bm021_postnumre.csv
  BM030 – liggetid i dage pr. kommune (2004-) → data/raw/bm030_kommuner.csv
  BM031 – liggetid i dage pr. postnummer (2004-) → data/raw/bm031_postnumre.csv

Kilde: Finans Danmarks statistikbank på rkr.statistikbank.dk. Der er ikke noget
officielt API, så scriptet udfylder det samme formular som hjemmesiden og
læser HTML-tabellen. Gæster må højst trække 20.000 tal pr. forespørgsel, så
vi henter én ejendomskategori ad gangen og deler områderne op i bidder.

Output i long format:
    omraade_kode,omraade_navn,ejendomskategori,kvartal,<kr_pr_m2 | antal_solgte | liggetid_dage>
"""

import csv
import html
import http.cookiejar
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://rkr.statistikbank.dk/statbank5a/SelectVarVal"
MAX_CELLS = 20000
CATEGORIES = {"1": "parcel", "2": "lejlighed"}  # "3" = fritidshus, springes over
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# Kommuner har 3-cifrede koder; "00" = hele landet. Regioner (08x) og landsdele (2 cifre) droppes.
KOMMUNER = lambda k: k == "00" or (len(k) == 3 and not k.startswith("08"))
ALLE = lambda k: True
# "vars" = (V1, VS1, VS2) for område og ejendomskategori. Tabeller med en ekstra variabel
# ("measure" = V3, VS3, valgt værdi) har tid som 4. variabel, ellers som 3.
PRIS = {"col": "kr_pr_m2"}
SALG = {"col": "antal_solgte"}
LIGGETID = {"col": "liggetid_dage"}

TABLES = {
    "BM010": {**PRIS, "vars": ("OMR20", "VM20NYKOM010", "VM20EJKAT010"), "measure": ("PRIS20", "VM20PRIS010", "REAL"),
              "keep": KOMMUNER, "out": RAW / "bm010_kommuner.csv"},
    "BM011": {**PRIS, "vars": ("PNR20", "VM20PNR11", "VM20EJKAT011"), "measure": ("PRIS20", "VM20PRIS011", "REAL"),
              "keep": ALLE, "out": RAW / "bm011_postnumre.csv"},
    "BM020": {**SALG, "vars": ("OMR20", "VM20NYKOM020", "VM20EJKAT020"), "measure": ("BEV20", "VM20BOL020", "SALG"),
              "keep": KOMMUNER, "out": RAW / "bm020_kommuner.csv"},
    "BM021": {**SALG, "vars": ("PNR20", "VM20PNR021", "VM20EJKAT020"), "measure": ("BEV20", "VM20BOL020", "SALG"),
              "keep": ALLE, "out": RAW / "bm021_postnumre.csv"},
    "BM030": {**LIGGETID, "vars": ("OMR20", "VM20NYKOM030", "VM20EJKAT030"),
              "keep": KOMMUNER, "out": RAW / "bm030_kommuner.csv"},
    "BM031": {**LIGGETID, "vars": ("PNR20", "VM20PNR031", "VM20EJKAT031"),
              "keep": ALLE, "out": RAW / "bm031_postnumre.csv"},
}

opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)


def get(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    with opener.open(url, body, timeout=120) as r:
        return r.read().decode("iso-8859-1")


def options(page, select_name):
    """Returnerer [(value, label)] for en <SELECT NAME=...> på definitionssiden."""
    m = re.search(rf'NAME="{select_name}".*?</SELECT>', page, re.S | re.I)
    return [
        (v, html.unescape(t).strip())
        for v, t in re.findall(r'<OPTION VALUE="([^"]+)"[^>]*>([^<]*)', m.group(0), re.I)
    ]


def fetch_table(table):
    cfg = TABLES[table]
    v1, vs1, vs2 = cfg["vars"]
    n = 4 if "measure" in cfg else 3  # tid er altid sidste variabel
    define = get(f"{BASE}/Define.asp?MainTable={table}")
    areas = [(k, n) for k, n in options(define, "var1") if cfg["keep"](k)]
    quarters = [q for q, _ in options(define, f"var{n}")]
    code_by_label = {n: k for k, n in areas}
    print(f"{table}: {len(areas)} områder, {len(quarters)} kvartaler ({quarters[-1]}–{quarters[0]})")

    chunk = MAX_CELLS // len(quarters)
    rows = []
    for cat, cat_name in CATEGORIES.items():
        for start in range(0, len(areas), chunk):
            form = [
                ("TS", f"ShowTable&OldTab=SELECT&SubjectCode=201&AntVar={n}&Contents=Indhold&tidrubr=rubrik{n}"),
                ("PLanguage", "0"), ("FF", "20"), ("OldTab", "SELECT"), ("SavePXSId", "0"),
                ("MainTable", table), ("SubTable", "S0"), ("SelCont", "Indhold"),
                ("Contents", "Indhold"), ("SubjectCode", "201"), ("antvar", str(n)),
                ("action", "urval"), ("guest", "-1"), ("GuestFileSize", str(MAX_CELLS)),
                ("MaxFileSize", str(MAX_CELLS)), ("V1", v1), ("V2", "EJKAT20"),
                ("VS1", vs1), ("VS2", vs2), (f"V{n}", "Tid"), (f"VS{n}", ""),
                (f"rubrik{n}", "kvartal"), ("tidrubr", f"rubrik{n}"), ("tfrequency", "4"),
                ("var2", cat),
            ]
            if "measure" in cfg:
                v3, vs3, value = cfg["measure"]
                form += [("V3", v3), ("VS3", vs3), ("var3", value)]
            form += [("var1", k) for k, _ in areas[start : start + chunk]]
            form += [(f"var{n}", q) for q in quarters]
            page = get(f"{BASE}/saveselections.asp", form)

            tbl = re.search(r'<table id="pxtable".*?</table>', page, re.S)
            if not tbl:
                raise SystemExit(f"Ingen tabel i svaret for {table} {cat_name} fra område {start}")
            header = re.findall(r'<th class="headfirst"[^>]*>([^<]*)</th>', tbl.group(0))
            cols = [h for h in header if re.fullmatch(r"\d{4}K\d", h)]
            # Områderne står i det inderste forspalte-niveau (stub3 med 4 variabler, stub2 med 3).
            for label, cells in re.findall(
                rf'<td class="stub{n - 1}"\s*>([^<]*)</td>(.*?)</tr>', tbl.group(0), re.S
            ):
                label = html.unescape(label).strip()
                values = re.findall(r"<td class=N\w*>([^<]*)</td>", cells)
                for q, v in zip(cols, values):
                    v = v.replace("\xa0", "").replace(" ", "").strip()
                    # 0 betyder "ikke offentliggjort" for priser, men er et gyldigt antal salg.
                    ok = v.isdigit() and (int(v) > 0 or cfg["col"] == "antal_solgte")
                    rows.append((code_by_label[label], label, cat_name, q, v if ok else ""))
        print(f"  {cat_name}: færdig")

    out = cfg["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["omraade_kode", "omraade_navn", "ejendomskategori", "kvartal", cfg["col"]])
        w.writerows(sorted(rows))
    print(f"  skrev {len(rows)} rækker til {out}")


if __name__ == "__main__":
    import sys
    for t in sys.argv[1:] or TABLES:  # fx: python3 scripts/fetch_prices.py BM020 BM021
        fetch_table(t)
