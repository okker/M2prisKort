#!/usr/bin/env bash
# Henter kommune- og postnummergrænser fra Dataforsyningen (DAWA) og forenkler dem til web-brug.
# Output:
#   web/data/kommuner.topo.json    – hele landet, objekt "kommuner" (kode, navn)
#   web/data/hovedstaden.topo.json – hovedstadsområdet, objekterne "postnumre" (pnr, navn, kode = kommunen
#                                    postnummeret overlapper mest med) og "kommuner" (kode)
set -euo pipefail
cd "$(dirname "$0")/.."

# Hovedstadsområdet som defineret i planloven (Fingerplanen): Region Hovedstaden uden Bornholm
# plus Greve, Køge, Lejre, Roskilde, Solrød og Stevns. Ret listen her for en anden afgrænsning.
HOVEDSTAD="101,147,155,185,151,153,157,159,161,163,165,167,169,173,175,183,187,190,201,210,217,219,223,230,240,250,260,270,253,259,265,269,336,350"

KOM=data/raw/kommuner.geojson
PNR=data/raw/postnumre.geojson
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p data/raw web/data
MS="npx --yes mapshaper@0.6"

[ -f "$KOM" ] || curl -sf -o "$KOM" "https://api.dataforsyningen.dk/kommuner?format=geojson&struktur=mini"
[ -f "$PNR" ] || curl -sf -o "$PNR" "https://api.dataforsyningen.dk/postnumre?format=geojson&struktur=mini"

# Hele landet. Christiansø (0411) er ikke en kommune og har ingen prisdata. Forenkl kraftigt
# (bevar små øer som Læsø/Ærø/Fanø) og behold kun de felter kortet bruger.
$MS "$KOM" \
  -filter "kode !== '0411'" \
  -filter-fields kode,navn \
  -filter-islands min-area=2km2 \
  -simplify interval=250 keep-shapes \
  -clean \
  -rename-layers kommuner \
  -o web/data/kommuner.topo.json format=topojson quantization=1e5

# Hovedstadsområdet: kommunegrænser (til orientering) og postnumre, mindre forenklet.
$MS "$KOM" \
  -filter "[$HOVEDSTAD].includes(+kode)" \
  -each "kode = +kode" \
  -filter-fields kode \
  -filter-islands min-area=1km2 \
  -simplify interval=60 keep-shapes \
  -clean \
  -o "$TMP/kommuner.json" format=geojson

# Boligmarkedsstatistikken slår de indre postnumre sammen (1000-1499, 1500-1799, 1800-1999),
# så de opløses til samme grupper. Et postnummer hører til området, hvis den kommune, det
# overlapper mest med, er med i listen. Postnumre til store modtagere har ingen boliger.
# DAWA's postnumre dækker også havet, så de klippes til kommunernes landareal. Undgå -clean her
# og kør -clip for sig: begge dele får ellers 2300 København S og 2791 Dragør til at forsvinde.
$MS "$PNR" \
  -filter "!stormodtager" \
  -each "pnr = +nr < 1500 ? 1000 : +nr < 1800 ? 1500 : +nr < 2000 ? 1800 : +nr" \
  -dissolve pnr copy-fields=navn \
  -join web/data/kommuner.topo.json fields=kode largest-overlap \
  -filter "[$HOVEDSTAD].includes(+kode)" \
  -each "kode = +kode" \
  -filter-fields pnr,navn,kode \
  -o "$TMP/postnumre_hav.json" format=geojson
$MS "$TMP/postnumre_hav.json" -clip "$TMP/kommuner.json" -o "$TMP/postnumre_land.json" format=geojson
$MS "$TMP/postnumre_land.json" \
  -filter-islands min-area=1km2 \
  -simplify interval=60 keep-shapes \
  -o "$TMP/postnumre.json" format=geojson

$MS -i "$TMP/postnumre.json" "$TMP/kommuner.json" combine-files \
  -o web/data/hovedstaden.topo.json format=topojson quantization=1e5
