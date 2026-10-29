# Hypotesregister

Varje hypotes formuleras innan den testas: regel, ekonomisk motivering, förregistrerat parameterrum och vad som skulle falsifiera den. Hypoteserna översätts till `hypotheses/<id>.yaml` enligt strategischemat i fas 5. Parameterrummen nedan är startpunkter; ändringar efter att en sökning körts kräver en ny version.

Primär benchmark för alla: likaviktat investerbart universum med samma rebalanseringsfrekvens och kostnader.

---

## H0 — Referens: likaviktat universum

Ingen selektion. Finns för att kalibrera motorn och ge baslinjen som allt annat jämförs med. Körs även i varianter per land och storlekssegment.

---

## H1 — Tidig compounder-talang

**Idé**: Hitta bolag med kort historik (3–5 år) som redan visar de egenskaper som framtida supervinnare hade, innan de blommar ut. Maximera vinsten från de som lyckas genom att låta dem växa i portföljen, och begränsa förlusterna från talangerna som inte lyckas.

**Motivering**: Marknaden underskattar varaktigheten i hög tillväxt kombinerad med hög lönsamhet, särskilt i små, mindre bevakade bolag. Avkastningen förväntas vara starkt högerskev.

**Första steg**: talangstudie (fas 8) på urvalsvillkoret innan strategin byggs. Hur ser fördelningen av framtida avkastning ut? Vilka egenskaper vid urval skiljer vinnare från förlorare?

**Selektion**
- `min_history_years` ∈ {2, 3, 5}
- omsättnings-CAGR över fönstret ≥ {10 %, 15 %, 20 %, 25 %}
- lönsamhet: ROIC eller ROE, medel över fönstret ≥ {10 %, 15 %, 20 %}
- konsistens som variant: tillväxt positiv i alla år / i ≥ 80 % av åren
- fönster ∈ {3, 5} år
- valfri värderingsvakt: värdering under egen historisk median, eller under percentil {50, 70} bland bolag som klarar övriga krav

**Positionshantering att jämföra**
- rebalanseringspolicy: ingen (låt drifta) / tak på {15 %, 20 %, 25 %} / periodisk till lika vikt
- pyramidering när fundamenta fortsatt uppfylls och kursen stigit: av / på med max {1, 2} tillägg

**Exits att jämföra**
- fundamental med buffert: sälj när kriterierna inte uppfylls {1, 2} rapportperioder i rad
- prisbaserad: trailing stop {25 %, 35 %, 50 %}, eller underprestation mot universum {20 %, 30 %} över 12 mån
- kombination av båda

**Falsifieras om**: överavkastningen mot likaviktat universum inte är positiv out-of-sample, eller om den helt försvinner när de 5 bästa bolagen tas bort, eller om talangstudien inte visar högre andel extrema vinnare än universum.

---

## H2 — Sammansatt kvalitet, tillväxt och värdering

**Idé**: Istället för hårda filter, ranka alla bolag på flera dimensioner och köp de högst rankade.

**Motivering**: Kombinationer av kvalitet och rimlig värdering har historiskt gett överavkastning i många marknader, och en mjuk ranking är mindre känslig för exakta trösklar än hårda filter.

**Dimensioner** (varje som percentil i universum)
- lönsamhet: ROIC, rörelsemarginal, FCF-marginal
- tillväxt: omsättnings- och vinst-CAGR, tillväxtkonsistens
- värdering: EV/EBIT, FCF-yield, värdering relativt egen historik
- balansräkning: nettoskuld/EBITDA, soliditet
- aktieägaravkastning: direktavkastning, utdelningstillväxt, utspädning

**Viktuppsättningar** (fördefinierade, ingen fri optimering): lika vikt / kvalitetstung / värderingstung / tillväxttung.

**Varianter**: mellanväg med hårda minimikrav på lönsamhet och skuldsättning, ranking på resten.

**Portfölj**: antal positioner ∈ {15, 25, 40}, rebalansering ∈ {kvartal, halvår}, rank-hysteres (köp topp N, sälj utanför topp {1,5N, 2N}).

**Falsifieras om**: ingen viktuppsättning slår benchmark out-of-sample, eller om resultatet bara håller för en enskild viktuppsättning.

---

## H3 — Stabila kassaflöden med timing

**Idé**: Bolag med ovanligt stabila och förutsägbara kassaflöden, kombinerat med en timingmekanism för när man köper.

**Motivering**: Stabila bolag har ofta lägre risk än marknaden prisar in (low-volatility/quality-anomali). Timing kan förbättra ingångspriset eller undvika perioder med svag trend.

**Selektion**
- FCF positivt i ≥ {80 %, 100 %} av åren över {5, 7} år
- låg variationskoefficient i FCF eller rörelseresultat (percentil ≤ {20, 30})
- valfri tillväxt ≥ 0 %

**Timingvarianter att jämföra**
- ingen timing (baslinje)
- trend: köp endast när kurs över {100, 200}-dagars medel
- värdering: köp endast när FCF-yield över egen historisk median
- återhämtning: köp efter nedgång på ≥ {15 %, 25 %} från 52-veckorshögsta med efterföljande stabilisering

**Falsifieras om**: timingvarianterna inte slår baslinjen utan timing, eller om strategin bara uppnår lägre volatilitet utan bättre information ratio.

---

## H4 — Djupvärde i nödlidande bolag

**Idé**: Köp de bolag som värderas som om de ska gå under. Många gör det, men de som överlever ger så stor avkastning att de väger upp förlusterna.

**Motivering**: Extrem pessimism och tvångsförsäljning kan leda till systematisk undervärdering. Avkastningsprofilen förväntas vara högerskev med många förluster.

**Kritiska förutsättningar**: kräver att avnoterade bolag och konkurser finns i datat och hanteras korrekt (fas 1 och 3). Utan det blir resultatet kraftigt överskattat. Kör alltid robusthetstestet med 0 % konkursåtervinning.

**Selektion**
- lägsta percentil {5, 10, 20} av P/B, P/S eller EV/S
- variant: kombinera med distressmått (Altman Z lågt) eller tvärtom med Piotroski F-score ≥ {5, 7} för att välja de som visar förbättring
- variant: momentum-skydd, kräv att 3-månaders avkastning inte är i lägsta decilen

**Portfölj**: många positioner ∈ {30, 50}, lika vikt, rebalansering {halvår, år}. Strikt likviditetsfilter, eftersom dessa bolag ofta är svårhandlade.

**Falsifieras om**: resultatet försvinner med realistiska kostnader och kapacitetsgränser, eller med 0 % återvinning vid konkurs.

---

## H5 — Enkla faktorbaslinjer: värde och momentum

**Idé**: De enklaste kända faktorerna, var för sig: lägst positivt P/E (värde) och högst avkastning senaste 12 månaderna exklusive senaste månaden (momentum, 12-1). Ingen kombination, ingen timing.

**Motivering**: Värde- och momentumpremier är väldokumenterade globalt. Här fungerar de som kontroll av hela kedjan (data, faktorer, motor, kostnader, trial-register) och som baslinjer som mer avancerade hypoteser ska slå. Om inte ens dessa syns i datan är det en varningssignal om datan eller motorn, eller att premierna är små i svenska aktier efter kostnader.

**Selektion**: `top_n_factor_v1`, område SE, period 2008-01-01–2026-10-27, 10 bps kostnad, likavikt. Förregistrerat parameterrum (24 konfigurationer):
- faktor: `pe_ratio` (lägst, endast positiva) eller `momentum_12_1m` (högst)
- antal innehav: 20, 30, 50
- rebalansering: månad, kvartal
- minsta omsättning (median 60 dagar): ingen, 1 MSEK per dag

**Entry/exit**: köp vid rebalansering (T+1), sälj när bolaget faller ur topp N.

**Portfölj**: likavikt, ingen maxvikt utöver 1/N.

**Falsifieras om**: medianen över parameterrummet inte slår `equal_weight_v1` SE efter kostnader, eller om resultatet hänger på en enstaka parameterkombination eller enstaka år. Jämförs också med percentilen bland 500 slumpportföljer (`random_pick_v1`, k = 30, månadsvis); notera att slumpportföljerna byter hela innehavet varje månad och därmed bär högre kostnader än en strategi med lägre omsättning.

**Resultat 2026-10-29** (experiment `h5_value_momentum_grid_se`, trials 28–51, 24 konfigurationer, 0 misslyckade; jämförelse med `equal_weight_v1` SE 2008–2026, CAGR 9,6 %):
- **Värde:** alla 12 slår likavikt; överavkastning median +3,1 %/år (min +1,1 %), informationskvot median 0,30, percentil bland slumpportföljer median 98,6 %. Stabilt över parametrar. Men ojämnt över tid: slår likavikt 11–12 år av 19, och utan de tre bästa åren (2009 +54, 2021 +31, 2025 +30 procentenheter för topp 30 månadsvis) är medelöveravkastningen −1,3 %/år.
- **Momentum:** 9 av 12 slår likavikt; median +0,8 %/år (−3,0 till +4,3), starkt beroende av antal innehav (topp 20 sämst, topp 50 bäst). Starkt 2013–2017 (+9,5 %/år), svagt 2023–2026 (−12,4 %/år).
- **Status:** inte falsifierad men inte bekräftad. Värdepremien finns i datan men hänger på ett fåtal år. Deflaterad Sharpe och PBO (24 försök) återstår. Börsdata saknar avnoterade bolag, vilket troligen gynnar värde mest (billiga bolag som gick i konkurs saknas).


---

## Överlägg som testas på alla hypoteser (stadium 4)

**Regim**: index eller likaviktat universum under {150, 200}-dagars medel, eller 12-månaders universumsavkastning negativ, eller andel bolag över 200-dagars medel under {30 %, 40 %}. Åtgärd: inga nya köp / exponering {50 %, 0 %}. Utvärderas på om det förbättrar riskjusterad avkastning och drawdown över många parameterval, inte om det räddar en enskild krasch.

---

## Mall för nya hypoteser

```
## H<n> — <namn>

**Idé**:
**Motivering**: varför ska detta ge överavkastning, och varför har det inte arbitragerats bort?
**Första steg**: (t.ex. talangstudie eller faktoranalys)
**Selektion**: regler + förregistrerat parameterrum
**Entry/exit**:
**Portfölj**:
**Falsifieras om**:
```
