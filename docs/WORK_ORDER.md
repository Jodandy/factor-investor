# Arbetsorder: factor-lab

Läs `CLAUDE.md` först. Invarianterna där gäller genom hela arbetsordern.

Arbetet är uppdelat i faser. Varje fas avslutas med acceptanskriterier som ska vara uppfyllda och verifierade innan nästa fas påbörjas. Efter varje fas: sammanfatta vad som byggts, vilka beslut som tagits (i `DECISIONS.md`), och vad som är osäkert. Vänta sedan på granskning.

---

## Fas 0 — Projektgrund

**Uppgift**

- Skapa repostrukturen enligt `CLAUDE.md`, `pyproject.toml` med `uv`, ruff, mypy och pytest konfigurerade.
- Docker Compose med PostgreSQL. Migreringar med Alembic.
- `config/settings.toml` med bland annat: databas-URL, sökväg till datakatalog, basvaluta `SEK`, default-fördröjningar för rapportpublicering.
- `.env` för `BORSDATA_API_KEY` (gitignored), `.env.example` incheckad.
- CLI-skelett med typer: `factor-lab ingest`, `build-pit`, `build-universe`, `build-panel`, `backtest`, `research`, `search`, `validate`, `report`.
- CI-liknande `make check` som kör ruff, mypy och pytest.

**Acceptans**

- `make check` passerar på tomt projekt.
- Databasen startar och migrering körs.

---

## Fas 1 — Datainhämtning från Börsdata

**Uppgift**

- Skriv en API-klient med rate limiting, retry med backoff och lokal cache av råsvar. Verifiera rate limit och endpoints mot Börsdatas officiella API-dokumentation; anta ingenting.
- Hämta för alla instrument som API-nyckeln ger tillgång till (global access): instrumentmetadata (land, marknad, sektor, bransch, noteringsdatum), dagliga kurser (OHLCV), rapporter (år, kvartal, rullande 12 där det finns), utdelningar/aktieutdelningar om tillgängligt, antal aktier över tid, samt index om tillgängligt.
- Spara råsvar som JSON (för spårbarhet) och normaliserade tabeller i PostgreSQL. Synken ska vara idempotent och inkrementell.
- **Dataaudit** (`docs/DATA_AUDIT.md`), mycket viktig. Svara konkret på:
  - Finns avnoterade bolag med, och i så fall med kurshistorik fram till sista handelsdag? Hur många per år?
  - Går det att avgöra avnoteringsorsak (uppköp, konkurs, byte av lista)? Om inte, vilka heuristiker kan användas?
  - Finns faktiskt publiceringsdatum per rapport? För hur stor andel av rapporterna? Hur ser fördelningen av (publiceringsdatum − periodslut) ut?
  - Revideras historiska rapporter i efterhand (restatements), och syns det i datat?
  - Är kurser justerade för splittar? Ingår utdelningar i någon totalavkastningsserie, eller måste den byggas?
  - Hur lång historik finns per bolag? Fördelning över år och per land.
  - Vilka index finns (OMX Stockholm GI, Carnegie Small Cap Return Index eller motsvarande)?
  - Kända luckor, dubbletter, uppenbart felaktiga värden.

**Acceptans**

- Full synk går att köra från tom databas och sedan inkrementellt.
- `DATA_AUDIT.md` besvarar alla frågor ovan med siffror.
- Om avnoterade bolag saknas helt: stoppa och rapportera, eftersom det påverkar hela projektets giltighet.

---

## Fas 2 — Point-in-time-lager

**Uppgift**

- Tabell `fundamentals_pit` där varje värde har `instrument_id`, `metric`, `period_end`, `period_type`, `value`, `known_from`.
- `known_from` = faktiskt publiceringsdatum om det finns. Annars konservativ fallback, konfigurerbar: kvartal = periodslut + 60 dagar, helår = periodslut + 90 dagar. Lägg alltid till 1 handelsdag så att rapporten inte kan påverka handeln samma dag.
- Om restatements finns: behåll varje version med sitt eget `known_from`. Uppslag per datum ska ge den version som var känd då.
- Funktion `as_of(date, instruments, metrics, history_years)` som returnerar den senaste kända historiken per bolag, inklusive tidigare års värden så som de var kända vid `date`.
- Härledda basmått beräknas här (med samma point-in-time-logik): ROIC, ROE, ROA, brutto-/rörelse-/nettomarginal, fritt kassaflöde, FCF-marginal, nettoskuld, nettoskuld/EBITDA, soliditet, räntetäckningsgrad, kapitalomsättning, utspädning (förändring i antal aktier), vinst per aktie, utdelning per aktie. Dokumentera exakta definitioner i `DECISIONS.md`.

**Acceptans**

- Integritetstest: för ett slumpmässigt urval av (bolag, datum) ska inget värde från `as_of` ha `known_from > date`.
- Integritetstest: en syntetisk rapport injicerad med `known_from = D` påverkar ingenting före `D`.
- Känslighetsrapport: andel rapporter som använder fallback-fördröjning per år.

---

## Fas 3 — Universum, bolagshändelser och valuta

**Uppgift**

- Totalavkastningsserie per instrument (justerad kurs + återinvesterade utdelningar), i lokal valuta och i SEK. FX-kurser behövs: hämta från Börsdata om de finns, annars från en dokumenterad extern källa (t.ex. Riksbanken) och lagra lokalt.
- Investerbart universum per datum, konfigurerbart: land/marknader, listor (inkl./exkl. First North m.fl.), lägsta kurs, lägsta median dagsomsättning över 60 dagar, lägsta antal års rapporthistorik (t.ex. 2, 3, 5 år; ska kunna vara kort eftersom unga bolag är en central målgrupp), uteslutna sektorer (t.ex. banker och fastigheter där nyckeltal inte är jämförbara, men som parameter, inte hårdkodat).
- Avnoteringshantering: positioner i ett bolag som avnoteras realiseras på sista handelskurs. Om orsaken bedöms vara konkurs eller tvångsrekonstruktion: konfigurerbar återvinningsgrad (default 0 %). Om orsak inte kan avgöras: dokumentera heuristik och kör känslighetsanalys. Detta är avgörande för djupvärdeshypoteser.
- Likviditetsbucket per bolag och datum (för kostnadsmodellen).

**Acceptans**

- Universumets storlek per år redovisas och ser rimlig ut.
- Integritetstest: inget bolag finns i universumet före sitt noteringsdatum eller efter sin avnotering, och inget filter använder framtida data (t.ex. framtida omsättning).
- Totalavkastning för några välkända bolag stämmer mot extern källa inom rimlig tolerans.

---

## Fas 4 — Faktorpanel

**Uppgift**

Bygg ett generativt faktorsystem, inte handskrivna faktorer. En faktor definieras som `basmått × transformation × normalisering`, och definitioner lever i ett register med metadata.

**Basmått** (fundamentala): alla från fas 2, plus värderingsmått beräknade med point-in-time-kurs: P/E, P/S, P/B, EV/EBIT, EV/EBITDA, EV/S, P/FCF, FCF-yield, direktavkastning, totalavkastning till ägare (utdelning + återköp − utspädning).

**Basmått** (pris): avkastning över 1, 3, 6, 12 månader, 12−1 momentum, volatilitet (60/250 dagar), max drawdown över 1 år, avstånd till 50/200-dagars glidande medelvärde, avstånd till 52-veckorshögsta, relativ styrka mot universum, omsättningstrend.

**Transformationer** (fönster i år ∈ {1, 2, 3, 5, 7, 10}, ska fungera även när bolaget har kortare historik än fönstret, då med `NaN` eller definierat beteende per faktor):
- nivå (senaste), medel, median, min, max
- CAGR, linjär trend (lutning), förändring mot föregående år
- stabilitet: standardavvikelse, variationskoefficient, andel år positivt, andel år över tröskel, längsta svit av förbättring
- acceleration (senaste årets tillväxt minus fönstrets snitt)
- för värdering: percentil relativt bolagets egen historik

**Normaliseringar** (per datum): rå, percentil i universum, percentil inom sektor, z-score (winsoriserad), rank.

**Sammansatta poäng**: en mekanism för att kombinera flera faktorer till en poäng med vikter, där varje komponent normaliseras först. Används för composite-strategier.

**Färdiga sammansatta mått** som ska finnas: Piotroski F-score, Altman Z (eller nordisk anpassning), en kassaflödesstabilitetspoäng, ett skuldsättnings-/överlevnadsmått för nödlidande bolag. Dokumentera definitionerna.

**Register-metadata** per faktor: id, familj (t.ex. `growth`, `profitability`, `value`, `quality_stability`, `momentum`, `distress`), basmått, fönster, minsta historik som krävs. Familj används senare för att uppskatta antalet effektivt oberoende tester.

**Lagring**: faktorvärden beräknas på ett rebalanseringsrutnät (default månadsvis sista handelsdagen, konfigurerbart), lagras som Parquet partitionerat på datum. Faktorer beräknas lat och cachas; panelen ska inte behöva innehålla alla tänkbara kombinationer i förväg.

**Acceptans**

- Integritetstest per faktorfamilj: värdet vid datum D är identiskt om panelen byggs med data trunkerad vid D jämfört med full data. (Detta är det viktigaste testet i hela projektet.)
- Täckningsrapport: andel bolag med giltigt värde per faktor och år.
- Spot-check mot manuellt uträknade värden för 5 bolag.

---

## Fas 5 — Strategischema

**Uppgift**

Definiera strategier deklarativt med pydantic, serialiserbart till YAML. Schemat ska täcka minst:

- **universe**: referens till universumskonfiguration
- **selection**:
  - `filters`: lista av villkor på faktorer, absoluta (`roic_mean_5y >= 0.15`) eller relativa (`pct_universe(ev_ebit) <= 0.2`)
  - `ranking`: faktor eller sammansatt poäng, riktning, antal eller andel att välja
  - `min_history_years`
- **entry**: villkor för nytt köp (t.ex. rank inom topp N, plus eventuell timing-signal som pris över 200-dagars medel eller momentum positivt)
- **exit**: lista av regler, valfri kombination av
  - fundamental: slutar uppfylla filter (med buffert, t.ex. tillåt ett års svikt), poängen faller under percentil X
  - rank-baserad med hysteres (köp i topp 20, sälj först utanför topp 40)
  - pris: trailing stop, fast stop, underprestation mot universum över N månader
  - tid: max innehavstid
- **sizing**: lika vikt, invers volatilitet, poängviktad, fast belopp vid köp
- **rebalance_policy**: ingen (låt vinnare driva), periodisk till målvikt, endast vid tak (trimma ner positioner över X %), bandbaserad
- **position_management**: pyramidering (öka när position går bra och/eller fundamenta förbättras, med max antal tillägg och tak), trimning vid svaghet, tak per position, tak per sektor
- **portfolio**: min/max antal positioner, kassa när det saknas kandidater (behåll kassa eller fyll upp befintliga)
- **regime_overlay**: signal (index under glidande medelvärde, negativt index-momentum, marknadsbredd under tröskel, volatilitetsregim) och åtgärd (inga nya köp, minska exponering till X %, gå i kassa), med fördröjning
- **rebalance_frequency**: månad, kvartal, halvår
- **costs**: referens till kostnadsmodell

Alla numeriska fält ska kunna ersättas med en sökparameter (`{search: [a, b, c]}` eller intervall) så att samma schema används för både enskilda körningar och sökningar.

**Acceptans**

- YAML-exempel för samtliga hypoteser i `HYPOTHESES.md` validerar mot schemat.
- Ogiltiga konfigurationer ger tydliga felmeddelanden.

---

## Fas 6 — Backtestmotor

**Uppgift**

- Daglig mark-to-market, beslut fattas på rebalanseringsdatum (och dagligen för prisbaserade exits om sådana är aktiva).
- Signal beräknas med data per dag T, order exekveras på T+1 öppningskurs (stängningskurs som fallback om öppning saknas, dokumenteras).
- Kostnadsmodell (`config/costs.yaml`): courtage (procent + minimum), halva spreaden beroende på likviditetsbucket, samt kapacitetsgräns: en order får högst vara X % av medianomsättningen, resten fylls inte eller sprids över flera dagar (konfigurerbart).
- Portföljstorlek som parameter (påverkar kapacitet och minimiavgifter).
- Ingen skatt (ISK-antagande), men en separat schablonintäktsavgift kan läggas på som parameter.
- Utdata: dagliga värden, innehav per dag, alla affärer med orsak (vilken regel utlöste), omsättning.
- Prestanda: en enskild backtest över 15 år med månadsvis rebalansering ska ta under en sekund efter att panelen är laddad. Profilera innan Numba införs.

**Integritetstester (`tests/integrity/`)**

- **Orakel**: en strategi som får fuska och se nästa månads avkastning ska ge absurt hög avkastning. Detta bekräftar att motorn kan upptäcka information; om den inte gör det är något fel.
- **Orakel blockerat**: samma orakel genom det vanliga faktorgränssnittet ska vara omöjligt att konstruera.
- **Slump**: 500 slumpportföljer ur universumet ska i snitt ge ungefär likaviktat universum minus kostnader.
- **Ingen handel**: strategi utan köp ger exakt kassaavkastning.
- **Benchmark-replikering**: strategi som köper hela universumet likaviktat replikerar benchmark-modulen exakt.
- **Fördröjningstest**: att flytta exekvering från T+1 till T ska förändra resultatet (bekräftar att fördröjningen faktiskt tillämpas).

**Acceptans**

- Alla integritetstester passerar.
- Affärsloggen för ett exempel kan följas manuellt för ett bolag från köp till sälj.

---

## Fas 7 — Benchmarks och mått

**Benchmarks**

- Likaviktat investerbart universum, samma rebalanseringsfrekvens och kostnader som strategin. Detta är primär benchmark.
- Börsvärdesviktat investerbart universum.
- Externa index om tillgängliga (OMX Stockholm GI, Carnegie Small Cap Return Index eller motsvarande).

**Mått**

- CAGR, volatilitet, Sharpe, Sortino, max drawdown, längsta tid under vatten, Calmar
- Överavkastning per år mot primär benchmark, tracking error, information ratio, beta
- Andel rullande 3-årsperioder som slår benchmark, sämsta rullande 3-årsperiod (absolut och relativt)
- Omsättning per år, genomsnittlig innehavstid, antal positioner över tid
- Per affär: träffsäkerhet, snittvinst/snittförlust, fördelning av utfall
- **Koncentration av avkastning**: andel av total vinst som kommer från de 5 % bästa affärerna, och resultat om de 5 bästa bolagen tas bort. Viktigt för hypoteser som bygger på få stora vinnare.
- Exponering mot storlek, värde och momentum (enkel regression mot faktorportföljer byggda i ramverket)

**Acceptans**

- Mått verifierade mot handräknade värden på en syntetisk avkastningsserie.

---

## Fas 8 — Forskningsverktyg

**Uppgift**

- **Talangstudie / eventstudie**: givet ett urvalsvillkor, ta alla bolag som uppfyller det på varje rebalanseringsdatum och mät avkastning framåt (3, 6, 12, 24, 36, 60 månader) relativt universum. Redovisa fördelningen (percentiler, skevhet, andel som når 2x/5x/10x, andel som tappar >50 % eller avnoteras med förlust). Möjlighet att dela upp på egenskaper vid urvalstillfället för att hitta tidiga tecken som skiljer vinnare från förlorare.
- **Faktoranalys**: information coefficient (Spearman) per datum och över tid, kvintil-/decilportföljer och spread, avtagande signal (IC vid olika horisonter), omsättning per kvintil.
- **Korrelation mellan faktorer** och klustring per familj.
- Allt detta loggas i trial-registret.

**Acceptans**

- Talangstudie kan köras från CLI med ett villkor i YAML och ger en HTML-rapport.

---

## Fas 9 — Validering och skydd mot överanpassning

**Uppgift**

- **Trial-register** (PostgreSQL-tabell): varje körning med tidsstämpel, hypotes-id, config-hash, full konfiguration, sökstadium, nyckeltal, samt vilken dataperiod som användes.
- **Walk-forward**: rullande eller expanderande träningsfönster, val av parametrar på träningsperioden enligt ett fördefinierat urvalskriterium, utvärdering på nästa period, sammansatt out-of-sample-kurva.
- **CPCV** (combinatorial purged cross-validation) med purging och embargo anpassat till innehavstider och rapportfördröjningar.
- **Deflated Sharpe Ratio** baserat på antal försök (både råa och uppskattade effektiva via faktorfamiljer och korrelation mellan försök).
- **PBO** (probability of backtest overfitting) via CSCV.
- **Platåanalys**: för varje parameter, hur förändras resultatet i grannskapet av vald punkt? Värmekartor för parameterpar. Ett resultat som bara håller i en smal topp flaggas.
- **Robusthetsbatteri**, körs på varje slutkandidat:
  - kostnader ×2 och ×3
  - exekvering fördröjd ytterligare 1 och 5 dagar, rebalansering förskjuten i kalendern (start vid olika månader)
  - delperioder (t.ex. per femårsperiod, upp- och nedmarknader)
  - per land, per storlekssegment, med och utan First North
  - utan de 5 bästa bolagen
  - längre fallback-fördröjning för rapporter
  - för djupvärde: konkursåtervinning 0 % och strängare konkursklassning
- **Pappershandel** (`validation.paper_trading`): slutkandidater körs framåt från ett fastställt startdatum på data som inte fanns när strategin byggdes. Startdatum och konfiguration registreras permanent i registret och får inte ändras i efterhand. (Ersätter fast holdout, beslut 2026-10-27.)

**Acceptans**

- DSR och PBO verifierade mot publicerade exempel eller simulerade data med känt svar (t.ex. ren brussökning ska ge hög PBO).
- Robusthetsbatteriet producerar en sammanfattande rapport per kandidat.

---

## Fas 10 — Sökorkestrering

**Uppgift**

- Hypoteser definieras i `hypotheses/*.yaml` med: id, beskrivning, ekonomisk motivering, basstrategi, förregistrerat parameterrum, urvalskriterium (vad som räknas som bäst), samt vad som skulle falsifiera hypotesen. Parameterrummet får inte ändras efter att sökningen körts utan att en ny version skapas (versionera filen, registret håller isär versionerna).
- Hierarkisk sökning i stadier:
  1. Selektion med standardiserad portfölj (lika vikt, månadsvis, inga extra regler)
  2. Portföljparametrar (antal positioner, viktning, rebalanseringspolicy)
  3. Trade management (exits, pyramidering, trimning)
  4. Regimöverlägg
  5. Grov gemensam sökning kring slutkandidaterna för att fånga interaktioner
- Stöd för fullt rutnät när rummet är litet och Optuna (TPE) när det är stort. Parallell körning över processer.
- Urvalskriterium ska vara konfigurerbart, default: information ratio mot likaviktat universum, med krav på max drawdown och andel slagna rullande 3-årsperioder. Inte CAGR.

**Acceptans**

- En hel hypotes kan köras från CLI genom alla stadier och resultera i en rankad kandidatlista med robusthetsrapport.

---

## Fas 11 — Rapportering

**Uppgift**

- HTML-rapport per strategi: equity-kurva mot benchmarks (log-skala), drawdown, årlig överavkastning, rullande 3-års överavkastning, innehav över tid, affärsfördelning, koncentration av avkastning, robusthetsresultat, DSR och PBO, antal försök bakom resultatet.
- Jämförelserapport mellan hypoteser.
- Varje rapport visar tydligt vilken dataperiod som använts.

**Acceptans**

- Rapport genereras för samtliga hypoteser i `HYPOTHESES.md`.

---

## Prioritering om tiden är knapp

Fas 0–4 och 6 måste vara rätt innan något resultat är meningsfullt. Fas 8 (talangstudien) kan påbörjas direkt efter fas 4 och ger tidiga insikter. Fas 9 måste vara klar innan några slutsatser dras om vilken strategi som är bäst.
