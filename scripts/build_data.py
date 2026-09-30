"""Bygger datafilerne til kortet:

  data/raw/bm010_kommuner.csv  (+ bm020, bm030) → web/data/priser.json              (alle kommuner + hele landet)
  data/raw/bm011_postnumre.csv (+ bm021, bm031) → web/data/priser_hovedstaden.json  (postnumrene i web/data/hovedstaden.topo.json)

Filerne indeholder kun grundserierne; web/index.html udleder resten (årlig ændring,
pris/indkomst og indeks for de enkelte boligtyper).

Pr. område og ejendomskategori (parcel, lejlighed):
  pris      – m²-pris, glidende gennemsnit over de seneste 4 kvartaler (fjerner sæsonudsving og
              en del støj fra små områder). Kræver mindst 3 af 4 kvartaler med data. Nominelle kr.
  pris_real – samme i faste priser (kroner i seneste kvartal). Hvert kvartal deflateres med
              forbrugerprisindekset (data/raw/fpi_kvartal.csv) FØR glatningen; at deflatere den
              glattede pris bagefter undervurderer prisen i år med høj inflation (op til ~5
              procentpoint i årlig ændring i 2022), så faste priser kan ikke udledes i browseren.
  liggetid  – dage fra udbud til salg, glattet på samme måde (fra 2004).

"samlet" kombinerer parcel-/rækkehuse og ejerlejligheder:
  index    – kædeindeks (start = 100); index_real er det samme på faste priser. Hvert kvartal er ændringen det vægtede gennemsnit af de to
             typers ændring i den glattede m²-pris siden forrige kvartal med data, vægtet med antal
             solgte boliger over de samme 4 kvartaler (bm020/bm021). Før 2004 findes der ikke antal
             salg, så der bruges områdets gennemsnitlige fordeling i 2004-2007. Et ændret mix af huse
             og lejligheder flytter derfor ikke indekset; kun prisudviklingen gør.
  anker    – [kvartal, m²-pris, m²-pris i faste priser] for "dagens boligmix": typernes glattede
             m²-pris vægtet med antal solgte i seneste kvartal med data. Browseren regner prisen
             tilbage i tiden med indekset (pris[t] = anker × index[t] / index[kvartal]), så den
             samlede m²-pris og pris/indkomst viser, hvad den samme blanding af huse og lejligheder
             har kostet, uden at et skiftende mix flytter kurven.
  liggetid – typernes liggetid vægtet med antal solgte, dvs. gennemsnittet over alle solgte boliger.

Øverst i filen:
  hovedstadKommuner – kun i priser.json: kommunekoderne i hovedstadsområdet.
  indkomst  – kun i priser.json: disponibel indkomst for par pr. kommune og kvartal, i 100 kr.
              (data/raw/indkomst_kommuner.csv). Årstallene placeres midt i året og interpoleres
              lineært; efter sidste indkomstår antages uændret realindkomst (indkomsten følger FPI).
              Postnumre bruger indkomsten i den kommune, de overlapper mest med (feltet "kode" i
              hovedstaden.topo.json).

Serierne er kodet kompakt med encode(): [startkvartal, første værdi, ændring, ændring, ...], hvor
null betyder "mangler" og ændringer regnes fra seneste kendte værdi. Indeks er gemt × 10.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
WEB = ROOT / "web" / "data"
FPI = RAW / "fpi_kvartal.csv"

WINDOW = 4
MIN_OBS = 3
FALLBACK_YEARS = ("2004", "2005", "2006", "2007")  # vægte før der findes antal salg


def rolling_mean(values):
    out = []
    for i in range(len(values)):
        window = [v for v in values[max(0, i - WINDOW + 1) : i + 1] if v is not None]
        out.append(sum(window) / len(window) if i >= WINDOW - 1 and len(window) >= MIN_OBS else None)
    return out


def encode(values, scale=1):
    """Kompakt serie: [startindeks, første værdi, ændring, ...]; None bevares som "mangler".

    Førende og afsluttende None fjernes. Værdierne ganges med scale og afrundes til heltal.
    Afkodes af decode() i web/index.html. Returnerer None, hvis serien er tom.
    """
    ints = [round(v * scale) if v is not None else None for v in values]
    known = [i for i, v in enumerate(ints) if v is not None]
    if not known:
        return None
    out, prev = [known[0]], 0
    for v in ints[known[0] : known[-1] + 1]:
        if v is None:
            out.append(None)
        else:
            out.append(v - prev)
            prev = v
    return out


def load_fpi(quarters):
    """FPI pr. kvartal. Mangler de nyeste kvartaler endnu, genbruges det seneste tal."""
    with FPI.open(encoding="utf-8") as f:
        fpi = {r["kvartal"]: float(r["fpi"]) for r in csv.DictReader(f)}
    out, last = [], None
    for q in quarters:
        if q in fpi:
            last = fpi[q]
        elif last is not None:
            print(f"Advarsel: intet FPI for {q}, bruger seneste kendte værdi")
        out.append(last)
    return out


def load_counts(src, quarters, keep):
    """Antal solgte pr. (kode, kategori) over de seneste 4 kvartaler, som liste pr. kvartal."""
    by_q = defaultdict(dict)
    with src.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kode = int(r["omraade_kode"])
            if keep(kode):
                by_q[(kode, r["ejendomskategori"])][r["kvartal"]] = int(r["antal_solgte"] or 0)
    counts = {}
    for key, d in by_q.items():
        fallback = sum(v for q, v in d.items() if q[:4] in FALLBACK_YEARS) / len(FALLBACK_YEARS)
        series = []
        for i, q in enumerate(quarters):
            window = [d[w] for w in quarters[max(0, i - WINDOW + 1) : i + 1] if w in d]
            series.append(sum(window) if len(window) == WINDOW else fallback)
        counts[key] = series
    return counts


def load_quarterly(src, col, quarters, keep):
    """Rå kvartalsværdier pr. (kode, kategori) som liste i kvartalsrækkefølge (None = mangler)."""
    by_q = defaultdict(dict)
    with src.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kode = int(r["omraade_kode"])
            if keep(kode) and r[col]:
                by_q[(kode, r["ejendomskategori"])][r["kvartal"]] = int(r[col])
    return {key: [d.get(q) for q in quarters] for key, d in by_q.items()}


def quarterly_income(quarters, fpi):
    """Disponibel indkomst for par pr. kommune og kvartal (nominelle kr.)."""
    annual = defaultdict(dict)
    with (RAW / "indkomst_kommuner.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            annual[int(r["omraade_kode"])][int(r["aar"])] = float(r["kr"])
    fpi_q = dict(zip(quarters, fpi))
    out = {}
    for kode, by_year in annual.items():
        last = max(by_year)
        # FPI midt i sidste indkomstår (gennemsnit af 2. og 3. kvartal) til fremskrivning.
        fpi_last = (fpi_q[f"{last}K2"] + fpi_q[f"{last}K3"]) / 2
        series = []
        for q, f_q in zip(quarters, fpi):
            t = int(q[:4]) + (int(q[-1]) - 0.5) / 4 - 0.5  # år målt fra årets midte
            y0 = int(t // 1)
            if y0 >= last:
                series.append(by_year[last] * f_q / fpi_last)
            else:
                w = t - y0
                series.append(by_year[y0] * (1 - w) + by_year[y0 + 1] * w)
        out[kode] = series
    return out


def chain_index(smooth_by_type, weights_by_type):
    """Vægtet kædeindeks over flere boligtyper (start = 100 i første kvartal med data)."""
    n = len(next(iter(smooth_by_type.values())))
    index, level, last = [None] * n, None, None
    for t in range(n):
        if level is None:
            if any(s[t] is not None for s in smooth_by_type.values()):
                level, last, index[t] = 100.0, t, 100.0
            continue
        links = [
            (weights_by_type[k][t], s[t] / s[last])
            for k, s in smooth_by_type.items()
            if s[t] is not None and s[last] is not None
        ]
        if not links:
            continue
        total = sum(w for w, _ in links)
        ratio = sum(w * r for w, r in links) / total if total > 0 else sum(r for _, r in links) / len(links)
        level *= ratio
        last, index[t] = t, level
    return index


def anchor(index, nominal_by_type, real_by_type, weights):
    """[t, pris, pris_real] i seneste kvartal t, hvor både indeks og mindst én typepris findes."""
    for t in reversed(range(len(index))):
        avail = [k for k, s in nominal_by_type.items() if s[t] is not None]
        if index[t] is None or not avail:
            continue
        w = {k: weights[k][t] for k in avail}
        if sum(w.values()) == 0:
            w = {k: 1 for k in avail}
        mix = lambda by_type: round(sum(w[k] * by_type[k][t] for k in avail) / sum(w.values()))
        return [t, mix(nominal_by_type), mix(real_by_type)]
    return None


def compact(**series):
    """Udelader tomme serier."""
    return {k: v for k, v in series.items() if v}


def build(src, counts_src, liggetid_src, out, keep=lambda kode: True, extra=None):
    raw = defaultdict(dict)  # (kode, kategori) -> {kvartal: pris}
    names = {}
    quarters = set()
    with src.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kode = int(r["omraade_kode"])
            if not keep(kode):
                continue
            names[kode] = r["omraade_navn"]
            quarters.add(r["kvartal"])
            raw[(kode, r["ejendomskategori"])][r["kvartal"]] = (
                int(r["kr_pr_m2"]) if r["kr_pr_m2"] else None
            )
    quarters = sorted(quarters)
    fpi = load_fpi(quarters)
    deflator = [fpi[-1] / v for v in fpi]
    counts = load_counts(counts_src, quarters, keep)
    liggetid = load_quarterly(liggetid_src, "liggetid_dage", quarters, keep)
    none = [None] * len(quarters)

    areas, smoothed, smoothed_real, lig = {}, defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for (kode, kat), by_q in raw.items():
        series = [by_q.get(q) for q in quarters]
        smoothed[kode][kat] = rolling_mean(series)
        smoothed_real[kode][kat] = rolling_mean([v * d if v is not None else None for v, d in zip(series, deflator)])
        lig[kode][kat] = [round(v) if v is not None else None
                          for v in rolling_mean(liggetid.get((kode, kat), none))]
        areas.setdefault(str(kode), {"navn": names[kode]})[kat] = compact(
            pris=encode(smoothed[kode][kat]), pris_real=encode(smoothed_real[kode][kat]), liggetid=encode(lig[kode][kat]))

    for kode, by_type in smoothed.items():
        weights = {k: counts.get((kode, k), [0] * len(quarters)) for k in by_type}
        # Liggetid for alle solgte boliger: typernes liggetid vægtet med antal solgte.
        samlet_lig = [
            sum(weights[k][t] * lig[kode][k][t] for k in avail) / sum(weights[k][t] for k in avail)
            if (avail := [k for k in by_type if lig[kode][k][t] is not None]) and sum(weights[k][t] for k in avail) > 0
            else None
            for t in range(len(quarters))
        ]
        index = chain_index(by_type, weights)
        areas[str(kode)]["samlet"] = compact(
            index=encode(index, 10),
            index_real=encode(chain_index(smoothed_real[kode], weights), 10),
            anker=anchor(index, by_type, smoothed_real[kode], weights),
            liggetid=encode(samlet_lig))

    data = {"kvartaler": quarters, "omraader": areas}
    if extra:
        data.update(extra(quarters, fpi))
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Skrev {len(areas)} områder x {len(quarters)} kvartaler til {out} ({out.stat().st_size // 1024} KB)")


def main():
    WEB.mkdir(parents=True, exist_ok=True)
    topo = json.loads((WEB / "hovedstaden.topo.json").read_text(encoding="utf-8"))
    pnrs = {g["properties"]["pnr"] for g in topo["objects"]["postnumre"]["geometries"]}
    hs_kommuner = sorted(g["properties"]["kode"] for g in topo["objects"]["kommuner"]["geometries"])

    # Landsfilen har også indkomsterne (bruges af begge visninger) og listen over kommuner i
    # hovedstadsområdet, så landskortet kan tegne omridset uden at hente hovedstadsfilerne.
    build(RAW / "bm010_kommuner.csv", RAW / "bm020_kommuner.csv", RAW / "bm030_kommuner.csv",
          WEB / "priser.json",
          extra=lambda quarters, fpi: {
              "indkomst": {str(k): encode(v, 0.01) for k, v in quarterly_income(quarters, fpi).items()},
              "hovedstadKommuner": hs_kommuner,
          })

    build(RAW / "bm011_postnumre.csv", RAW / "bm021_postnumre.csv", RAW / "bm031_postnumre.csv",
          WEB / "priser_hovedstaden.json", keep=lambda k: k in pnrs)


if __name__ == "__main__":
    main()
