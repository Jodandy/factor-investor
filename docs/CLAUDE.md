# factor-investor — instruktioner för Claude Code

## Syfte

Ett forskningsramverk för att backtesta aktiestrategier på global data från Börsdata, utan lookahead bias och med strikt skydd mot överanpassning. Målet är inte att hitta den strategi som gav högst historisk avkastning, utan den som är mest robust: stabil överavkastning mot ett relevant benchmark, över många parameterval, delperioder och marknadssegment.

Ramverket ska kunna uttrycka och testa väldigt olika strategityper med samma maskineri, t.ex. växande kvalitetsbolag med kort historik, stabila kassaflöden med timing, och djupvärde i nödlidande bolag. Det får därför aldrig hårdkodas mot en specifik strategi.

Detaljerad arbetsorder: `docs/WORK_ORDER.md`. Hypoteser: `docs/HYPOTHESES.md`.

## Oförhandlingsbara invarianter

Dessa regler gäller all kod i projektet. Bryt aldrig mot dem, inte ens tillfälligt eller "för att testa". Om en uppgift verkar kräva det, stanna och fråga.

1. **Point-in-time.** All fundamental data slås upp via sitt `known_from`-datum, aldrig via periodslut. En rapport får inte användas före den dag den publicerades. Saknas publiceringsdatum används en konservativ fördröjning (se WORK_ORDER fas 2).
2. **Exekveringsfördröjning.** En signal beräknad med data per dag T får tidigast exekveras på dag T+1. Ingen handel på samma kurs som signalen beräknades från.
3. **Inga överlevare-filter.** Avnoterade bolag (uppköp, konkurs, avnotering) ingår i universumet för de datum de var noterade. Ingen kod får filtrera på "finns idag".
4. **Holdout är låst.** Perioden från `HOLDOUT_START` (i `config/settings.toml`) och framåt får endast läsas av `factor_investor.validation.final_holdout`, som kräver en explicit flagga och loggar varje körning permanent. All övrig kod ska klippa data vid `HOLDOUT_START` och ett test ska verifiera det.
5. **Varje körning registreras.** Varje backtest som körs inom en sökning eller ett experiment loggas i trial-registret (konfiguration, config-hash, hypotes-id, nyckeltal). Ingen körning får göras "vid sidan av" registret i forskningssyfte. Antalet försök används i deflated Sharpe och PBO.
6. **Kostnader är alltid på.** Transaktionskostnader och likviditetsbegränsningar är påslagna som default. Att stänga av dem kräver en explicit flagga och resultatet märks som "gross".
7. **Determinism.** Samma konfiguration och samma data ger exakt samma resultat. Alla slumpkällor har seed.
8. **Lookahead-testerna ska alltid passera.** Testsviten under `tests/integrity/` körs vid varje ändring i data-, faktor- eller motorlagret.

## Teknisk stack

- Python 3.12, beroenden hanteras med `uv`
- PostgreSQL för rådata och normaliserade tabeller (Docker Compose för lokal databas)
- Parquet + DuckDB/Polars för faktorpanel och analys
- numpy, med Numba där backtestloopen behöver det
- pydantic v2 för alla konfigurationer, YAML som filformat
- Optuna för parametersökning
- pytest, ruff, mypy (strict på `core`, `engine`, `pit`)
- typer för CLI
- Plotly för rapporter (statisk HTML)

## Projektstruktur

```
factor-investor/
  CLAUDE.md
  docs/            WORK_ORDER.md, HYPOTHESES.md, DECISIONS.md, DATA_AUDIT.md
  config/          settings.toml, costs.yaml
  hypotheses/      en YAML per hypotes med förregistrerat parameterrum
  src/factor_investor/
    ingest/        Börsdata-klient, synk, rålagring
    pit/           point-in-time-lager, as_of-uppslag
    universe/      investerbart universum, bolagshändelser, FX
    factors/       faktordefinitioner, transformationer, panelbygge
    strategy/      pydantic-schema för strategier
    engine/        simuleringsloop, exekvering, kostnader
    benchmarks/
    metrics/
    research/      talangstudier, IC, kvantilanalys
    validation/    walk-forward, CPCV, deflated Sharpe, PBO, robusthet, final_holdout
    search/        körning av hypoteser, Optuna, trial-register
    reporting/
    cli.py
  tests/
    unit/
    integrity/     lookahead- och överlevartester
  data/            (gitignored) parquet, cache
```

## Arbetssätt

- Arbeta en fas i taget enligt `docs/WORK_ORDER.md`. Varje fas har acceptanskriterier. Gå inte vidare förrän de är uppfyllda, och stanna för granskning efter varje fas.
- Logga alla icke-triviala designbeslut i `docs/DECISIONS.md` (datum, beslut, motivering, alternativ som valdes bort).
- Hitta inte på detaljer om Börsdatas API. Verifiera endpoints, fält och rate limits mot den officiella dokumentationen och mot faktiska svar, och dokumentera i `docs/DATA_AUDIT.md`.
- Skriv tester samtidigt som koden, inte efteråt. Varje ny faktor ska ha ett test som visar att den bara använder data känd vid beräkningsdatumet.
- Föredra enkel, läsbar kod framför smart kod. Optimera prestanda först när en profilering visar att det behövs.
- Svara användaren på svenska. Kod, identifierare och kommentarer på engelska.
