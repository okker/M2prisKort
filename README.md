# M2prisKort – boligpriser i bevægelse (POC)

Animeret Danmarkskort over m²-priser pr. kommune, 1992–i dag, til at undersøge
"ripple-effekten": stiger priserne først i København og spreder sig derefter udad?

## Kør lokalt

```bash
python3 -m http.server 8765 -d web
```

Åbn http://localhost:8765. Mellemrum = play/pause, klik på et område for at følge det, scroll for at zoome.
Knappen "Hovedstadsområdet" (eller dobbeltklik inden for den stiplede linje) skifter til postnumre; Esc går tilbage.

## Opdater data

```bash
python3 scripts/fetch_prices.py   # m²-priser (BM010/011), antal salg (BM020/021), liggetider (BM030/031) → data/raw/
python3 scripts/fetch_cpi.py      # forbrugerprisindeks fra Danmarks Statistik → data/raw/fpi_kvartal.csv
python3 scripts/fetch_income.py   # disponibel indkomst for par pr. kommune (DST INDKF132) → data/raw/indkomst_kommuner.csv
scripts/build_geo.sh              # kommune- og postnummergrænser fra Dataforsyningen → web/data/*.topo.json (kræver Node)
python3 scripts/build_data.py     # deflaterer, glatter, beregner årlig ændring → web/data/priser*.json
```

Kun Python-standardbiblioteket bruges; `build_geo.sh` kører mapshaper via `npx`.

### Dataformat

`web/data/priser*.json` indeholder kun grundserierne (glattet m²-pris i løbende og faste priser, liggetid,
samlet indeks og indkomst), kodet som `[startkvartal, første værdi, ændring, ændring, …]`. Browseren afkoder
dem og beregner årlig ændring, pris/indkomst og indeks pr. boligtype (`prepare()` i `web/index.html`).
Hovedstadsfilerne hentes først, når visningen åbnes. Ved første visning hentes ca. 220 KB data (gzip),
og hovedstadsvisningen henter yderligere ca. 180 KB.

Faste priser gemmes som egen serie, fordi de skal deflateres pr. kvartal *før* glatningen; at deflatere den
glattede pris i browseren giver op til ~5 procentpoint forkert årlig ændring i år med høj inflation.

## Data og forbehold

- **Priser:** Boligmarkedsstatistikken (Finans Danmark), tabel BM010, realiserede handelspriser i kr./m²,
  kvartalsvis 1992K1–. Kun frie handler via ejendomsmægler. Tallene er allerede omregnet til de 98 nuværende kommuner.
- **Metodebrud:** Tal før 2004 er opgjort anderledes og skaleret til niveauet i 2004K1.
- **Små kommuner:** Kvartaler med 5 handler eller færre er udeladt (vises gråt). Ejerlejligheder mangler i
  ca. 28 % af kommune-kvartalerne, parcel-/rækkehuse kun i ca. 1 %.
- **Alle boliger** (standard) er et kædeindeks, der kombinerer huse og lejligheder: hvert kvartal vægtes de to
  typers prisændring med antal solgte boliger (BM020/BM021). Før 2004 findes der ikke antal salg, så der bruges
  områdets fordeling i 2004–2007. Et gennemsnit af m²-priserne ville ændre sig, bare fordi mixet af huse og
  lejligheder ændrer sig, så m²-pris og pris/indkomst for alle boliger viser i stedet **dagens boligmix**:
  typernes m²-pris vægtet med antal solgte i seneste kvartal, regnet tilbage i tiden med det samlede indeks.
- **Pris/indkomst:** prisen for en bolig på 100 m² (glattet m²-pris × 100) delt med gennemsnitlig disponibel
  indkomst for par i kommunen. Par frem for alle familier, fordi Københavns mange enlige ellers trækker indkomsten
  ned (2024: 418.000 mod 730.000 kr.). Årstal interpoleres til kvartaler; efter sidste indkomstår (2024) antages
  uændret realindkomst. Postnumre bruger kommunens indkomst, så inden for én kommune viser målet kun prisforskelle.
- **Liggetid:** dage fra udbud til salg (BM030/BM031), fra 2004, glattet over 4 kvartaler. "Alle boliger" er
  gennemsnittet over alle solgte boliger (typerne vægtet med antal salg).
- **Glatning:** Glidende gennemsnit over 4 kvartaler (kræver 3 af 4). Den årlige ændring halter derfor ca. et halvt år.
- **Faste priser** (standard) er deflateret med forbrugerprisindekset og udtrykt i kroner i seneste kvartal
  med prisdata. Danmarks Statistik lagde FPI om i 2026: den nye PRIS01 starter 2000M12, så 1992–2000 kommer
  fra den lukkede PRIS113, skaleret til PRIS01's niveau (forholdet er konstant i overlappet 2000–2025).
  Er FPI for det seneste kvartal ikke udkommet endnu, genbruges seneste kendte kvartal. Knappen
  "Løbende priser" viser de nominelle tal.
- **Hovedstadsområdet** følger planlovens/Fingerplanens afgrænsning: Region Hovedstaden uden Bornholm plus
  Greve, Køge, Lejre, Roskilde, Solrød og Stevns (34 kommuner, 107 postnumre). Listen står i `scripts/build_geo.sh`.
  Et postnummer er med, hvis det overlapper mest med en af de 34 kommuner.
- **Postnumre:** BM011 slår de indre postnumre sammen til 1000-1499 (Kbh K), 1500-1799 (Kbh V) og 1800-1999
  (Frederiksberg C). Dataforsyningens postnumre dækker også havet og klippes derfor til kommunernes landareal.
  I indre by findes stort set kun ejerlejligheder, så vælg den boligtype der.
