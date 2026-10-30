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

**Förregistrering v1 (2026-10-29)**: `config/strategies/h2_composite_v1.yaml`, område SE, 2008-01-01–2026-10-27, 10 bps, minsta omsättning 1 MSEK/dag (median 60 dagar). Dimensionernas vikt delas lika på dess mått (percentil i universum efter filtret); ett bolag rankas bara om minst 75 % av vikten har data:
- lönsamhet: ROIC, rörelsemarginal, FCF-marginal
- tillväxt: omsättningstillväxt 1 år, vinsttillväxt 1 år
- värdering: EV/EBIT (lågt), FCF-yield (högt), P/E mot egna 5 år (lågt); negativt EV/EBIT eller P/E (förlust) ger sämsta värde
- balansräkning: soliditet, kassalikviditet (current ratio)
- aktieägaravkastning: direktavkastning

Avvikelser från idén ovan, eftersom måtten saknas i basdatan: ingen flerårs-CAGR eller tillväxtkonsistens, nettoskuld/EBIT ersatt av current ratio (tvetydigt tecken), ingen utdelningstillväxt eller utspädning.

Parameterrum (24): viktuppsättning {lika (alla 1), kvalitetstung (lönsamhet och balansräkning 2), värderingstung (värdering 3), tillväxttung (tillväxt 3)} × antal positioner {15, 25, 40} × rebalansering {kvartal, halvår}. Fast: rank-hysteres 1,5N, ren ranking utan hårda minimikrav (de axlarna kan bli egna experiment).

**Känd svaghet i v1**: engångsintäkter (t.ex. licensintäkter i bioteknikbolag) ger extrema marginaler och låga P/E på ett enda års siffror.

**Resultat 2026-10-29** (experiment `h2_composite_v1_se`, trials 76–99, 0 misslyckade). Jämfört med kontrollen `h0_liquid_equal_weight_se` (likavikt över samma likvida universum, samma rebalansering; trials 100–101):
- alla 24 konfigurationer slår kontrollen; överavkastning median +4,0 %/år (min +2,1 %), informationskvot median ~0,5
- slår kontrollen i 7 av 8 tidsblock (median), svagast 2024–2026
- alla fyra viktuppsättningar fungerar (median +3–5 %/år); tillväxttung svagast
- CSCV: PBO 71 % (att välja bästa parametrar hjälper inte), men konfigurationen som är bäst in-sample förlorar mot kontrollen out-of-sample i bara 1 % av uppdelningarna; deflaterad Sharpe för bästa konfigurationen 97 % (24 försök)
- mot `equal_weight_v1` (hela universumet): +2,1 till +7,5 %/år, PBO 44 %, deflaterad Sharpe 93 %; blocket 2022–2024 stort (småbolagskrasch)

**Status:** inte falsifierad. Kriteriet ("ingen viktuppsättning slår benchmark out-of-sample, eller bara en") uppfylls inte: alla fyra slår kontrollen, i nästan alla perioder. Reservationer: Börsdata saknar avnoterade bolag (överskattar troligen), få likvida bolag tidigt (67 år 2009), engångsintäkter i v1, inga nya data sedan hypotesen formulerades. Nästa steg: variantaxlarna (hårda minimikrav, hysteres), robusthet mot avnoteringar, och framåtriktad pappershandel innan något används på riktigt.

**Andra marknader, förregistrerat 2026-10-29**: samma regler och parameterrum (24) i Norge, Finland, Danmark och Europa (Stoxx 600-likt, i EUR): `h2_composite_{no,fi,dk,eu}_v1`, var och en mot sin kontroll `h0_liquid_equal_weight_{no,fi,dk,eu}_v1` (likavikt över samma likvida universum). Omsättningsgolv ungefär 1 MSEK/dag: 1 MNOK, 100 kEUR, 0,7 MDKK, 100 kEUR. Alla körningar räknas i H2:s antal försök. Bekräftas om flertalet marknader visar samma mönster som Sverige (de flesta konfigurationer slår kontrollen i de flesta perioder); i de nordiska grannländerna är universumet litet tidigt (10–20 bolag 2009), så urvalet betyder mest under senare år.

**Resultat andra marknader 2026-10-29** (trials 104–229; varje konfiguration mot kontrollen med samma rebalansering; H2 har nu 120 konfigurationer):

| Marknad | Överavkastning mot kontroll, median (min–max) | Slår kontrollen | Block slagna, median | PBO | Bästa in-sample förlorar OOS | Deflaterad Sharpe (120 försök) |
|---|---|---|---|---|---|---|
| SE | +4,0 % (+2,1 – +7,4) | 24/24 | 88 % | 71 % | 1 % | 94 % |
| NO | +5,9 % (+3,6 – +9,1) | 24/24 | 88 % | 63 % | 0 % | 99 % |
| FI | +2,6 % (+0,4 – +5,2) | 24/24 | 75 % | 64 % | 9 % | 91 % |
| DK | +3,6 % (+1,7 – +5,3) | 24/24 | 75 % | 50 % | 4 % | 96 % |
| EU | +4,1 % (+1,0 – +5,7) | 24/24 | 75 % | 70 % | 6 % | 91 % |

Alla viktuppsättningar slår kontrollen i alla marknader (median per uppsättning +1,8 till +6,3 %/år). Parameterval är fortfarande brus (PBO 50–71 %), men familjen som helhet håller. Mönstret från Sverige upprepas, alltså bekräftat enligt förregistreringen. Reservationer: marknaderna är inte oberoende (Europa innehåller de nordiska bolagen, samma globala faktorregimer), Börsdata saknar avnoterade bolag i alla marknader, och engångsintäkter i v1.

**USA, förregistrerat 2026-10-29**: `h2_composite_us_v1` mot `h0_liquid_equal_weight_us_v1`, samma regler och parameterrum (24), omsättningsgolv 100 kUSD/dag. Varning: Börsdata har bara bolag som är noterade i dag (1 625 amerikanska bolag i universumet 2008 mot omkring 5 000 noterade då), så alla absoluta avkastningar är kraftigt överskattade. Jämförelsen mot kontrollen är delvis skyddad (båda väljer bland samma överlevare), men den visar inte om H2 hade valt bolag som senare försvann.

**Resultat USA 2026-10-29** (trials 230–255): H2 förlorar mot kontrollen i alla 24 konfigurationer, median −3,3 %/år (−5,2 till −1,3), i alla viktuppsättningar. Slår kontrollen i 38 % av blocken; störst förluster 2017–2022 (−29 och −40 procentenheter per block), när breda tillväxtbolag drog ifrån och värde- och utdelningsbolag släpade. CSCV: bästa in-sample förlorar out-of-sample i 94 % av uppdelningarna; deflaterad Sharpe 5 % (144 försök). H2 median-CAGR 8,6 % mot kontrollens 11,7–12,0 % och börsvärdesviktat 11,8 %.

**Samlad status H2:** håller i Sverige, Norge, Finland, Danmark och Europa, men inte i USA. Alltså ingen universell premie i den här formen: antingen marknadsspecifik (mindre, mindre bevakade marknader), periodberoende (USA:s tillväxtdominans 2017–2022), eller påverkad av att amerikanska data bara innehåller överlevare (kontrollen av överlevare är ovanligt stark, 11,7 %/år). Kan inte avgöras med dessa data.

**v2, förregistrerat 2026-10-29**: `h2_composite_v2` (SE) och `h2_composite_us_v2` (USA). Som v1 men lönsamhet och tillväxt från bolagets egen historik (en ögonblicksbild per år, samma månad, minst 3 av 5 år), så att ett enskilt år (engångsintäkter) väger mindre:
- lönsamhet: 5-årsmedian av ROIC, rörelsemarginal, FCF-marginal
- tillväxt: 5-årsmedian av omsättningstillväxt, andel år med positiv omsättningstillväxt (konsistens), 5-årsmedian av vinsttillväxt
- värdering, balansräkning, aktieägaravkastning och parameterrum (24) oförändrade

Period 2010-01-01–2026-10-27 (historiken kräver data från 2008); kontrollerna körs om för samma period (`h0_liquid_equal_weight_{se,us}_2010`). Frågan: blir resultatet bättre eller sämre än v1 under samma period, och ändras bilden i USA?

**Resultat v2 2026-10-29** (trials 256–313; fyra avbrutna körningar 257–261 markerade som misslyckade och omkörda; kontrollerna gav identiskt resultat båda gångerna). Mot kontrollen med samma rebalansering, 2010–2026; v1 jämförs över samma månader:

| | Överavkastning median (min–max) | Före kontrollen | Block slagna, median | PBO | Bästa in-sample förlorar OOS | Deflaterad Sharpe (192 försök) |
|---|---|---|---|---|---|---|
| SE v1 | +4,1 % (+2,5 – +7,1) | 24/24 | 75 % | | | |
| SE v2 | +4,2 % (+3,2 – +7,8) | 24/24 | 75 % | 63 % | 3 % | 98 % |
| USA v1 | −4,1 % (−6,5 – −2,0) | 0/24 | 25 % | | | |
| USA v2 | −0,6 % (−2,3 – +0,9) | 6/24 | 38 % | 76 % | 71 % | 28 % |

Flerårshistorik i stället för ett års siffror: i Sverige lika bra i snitt men jämnare (sämsta konfigurationen +3,2 % mot +2,5 %, tillväxttung +5,2 % mot +2,9 %), med tyngdpunkt senare år. I USA försvinner det mesta av förlusten (−0,6 % mot −4,1 %), men ingen överavkastning: H2 är i USA fortfarande inte bättre än likavikt bland likvida bolag. Tolkning: v1:s förlust i USA berodde till stor del på ettårssiffror (engångseffekter, cykliska toppar); en stabilare kvalitetsbild tar bort förlusten men skapar ingen premie där.

**v2 i Norge, Finland, Danmark och Europa, förregistrerat 2026-10-29**: `h2_composite_{no,fi,dk,eu}_v2`, samma regler som `h2_composite_v2` och samma omsättningsgolv som v1 i respektive marknad, period 2010-01-01–2026-10-27, mot kontrollerna `h0_liquid_equal_weight_{no,fi,dk,eu}_2010`. Frågan: håller v2 minst lika bra som v1 där v1 fungerade, och blir det jämnare?

**Resultat v2 alla marknader 2026-10-29** (trials 314–417; H2 har nu 288 konfigurationer). Överavkastning mot kontrollen, median (min–max), 2010–2026:

| Marknad | v1 | v2 | v2 före kontrollen | v2 PBO | v2 deflaterad Sharpe |
|---|---|---|---|---|---|
| SE | +4,1 % (+2,5 – +7,1) | +4,2 % (+3,2 – +7,8) | 24/24 | 63 % | 98 % (192 försök) |
| NO | +5,1 % (+2,9 – +8,4) | +5,2 % (+2,8 – +8,2) | 24/24 | 47 % | 96 % |
| FI | +2,9 % (+0,5 – +5,8) | +1,6 % (+0,3 – +4,3) | 24/24 | 36 % | 81 % |
| DK | +3,1 % (+1,3 – +4,8) | +2,0 % (−0,5 – +4,4) | 23/24 | 50 % | 60 % |
| EU | +3,7 % (−0,0 – +6,1) | +0,9 % (−3,4 – +3,3) | 17/24 | 47 % | 38 % |
| USA | −4,1 % (−6,5 – −2,0) | −0,6 % (−2,3 – +0,9) | 6/24 | 76 % | 28 % |

**Slutsats:** v2 är ingen allmän förbättring. Flerårshistorik hjälper i USA, är oförändrad i Sverige och Norge och sämre i Finland, Danmark och särskilt Europa. Ettårssiffrorna i v1 verkar fånga något verkligt (senaste årets lönsamhet och tillväxt, "fundamental momentum") som femårsmedianer späder ut. Att välja version per marknad vore överanpassning. v1 står kvar som huvudversion; v2 visar att resultatet i Europa delvis kommer från färsk information, inte bara stabil kvalitet.

**Stresstest mot saknade konkurser, förregistrerat 2026-10-29**: `h2_composite_v1` (SE, alla 24) och kontrollen `h0_liquid_equal_weight_v1` under scenariot `bankruptcy` med årlig konkursfrekvens {2 %, 5 %} × slumpfrö {1, 2}, svaga bolag (ROIC ≤ 0 eller okänd, soliditet < 30 %) fyra gånger så utsatta; period 2008–2026. Experiment `h2_stress_bk{2,5}_s{1,2}_se` och `h0_stress_bk{2,5}_s{1,2}_se`. H2 klarar testet om överavkastningen mot kontrollen (samma scenario) i median är kvar på minst hälften av den ostressade (+4,0 %/år).

**Resultat stresstest 2026-10-29** (trials 418–521, 104 körningar, 0 misslyckade):

| Scenario | H2 CAGR (median) | Kontroll | Överavkastning median (min) | Före kontrollen |
|---|---|---|---|---|
| Ingen stress | 14,3 % | 10,1 % | +4,0 % (+2,1) | 24/24 |
| 2 %/år, frö 1 | 11,8 % | 7,7 % | +4,0 % (+1,3) | 24/24 |
| 2 %/år, frö 2 | 12,5 % | 8,6 % | +3,8 % (+2,4) | 24/24 |
| 5 %/år, frö 1 | 10,4 % | 6,1 % | +4,3 % (+1,7) | 24/24 |
| 5 %/år, frö 2 | 10,5 % | 6,1 % | +4,1 % (+2,5) | 24/24 |

Klarar testet: konkurserna sänker båda portföljernas avkastning med 2–4 procentenheter per år, men överavkastningen mot kontrollen ligger kvar (+3,8 till +4,3 %/år). H2 undviker svaga bolag ungefär lika mycket som konkurserna drabbar dem, så de saknade avnoterade bolagen förklarar inte H2:s försprång i Sverige. De absoluta avkastningarna är däremot troligen överskattade med några procentenheter per år.

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
- **Validering (CSCV, 8 block, överavkastning mot likavikt):** PBO 86 %: konfigurationen som är bäst i ena halvan av historiken hamnar under medianen i den andra i 86 % av de 70 uppdelningarna, och förlorar mot likavikt där i 51 %. Att välja "bästa" parametrar ger ingenting (out-of-sample Sharpe 0,00 mot 0,19 för medianen). Deflaterad Sharpe för bästa konfigurationen (momentum topp 50 månadsvis, informationskvot 0,37): 70 %, under 95 %. Värde utan likviditetsfilter svänger från −62 % till +78 % mot likavikt mellan block (illikvida småbolag); med filtret 1 MSEK lugnare.
- **Slutsats:** premierna syns i snitt (medianen slår likavikt) men är inte robusta över tid, och parameterval är brus. Inget av detta går vidare som strategi; H5 står kvar som baslinje.


---

## H6 — Greenblatts magiska formel

**Idé**: Joel Greenblatts regel (The Little Book That Beats the Market, 2005): ranka bolag på avkastningsgrad (EBIT/EV) och avkastning på kapital (EBIT/(rörelsekapital + anläggningstillgångar)), summera rankningarna och köp de bästa. Håll ungefär ett år.

**Motivering**: Bra bolag till lågt pris; publicerad regel, så 2008–2026 är i praktiken out-of-sample för den. Testar om en enkel, känd kombination av kvalitet och värdering håller i Sverige efter publiceringen.

**Förregistrering v1 (2026-10-29)**: `config/strategies/magic_formula_v1.yaml`, SE, 2008-12-01–2026-10-27 (start i december så att årlig och kvartalsvis rebalansering båda investerar från första rebalanseringen), 10 bps.
- universum: omsättning ≥ 1 MSEK/dag, utan finans och fastighet (Börsdata sektor 1) och kraftförsörjning (10); sektorn är Börsdatas nuvarande (ingen historik)
- avkastningsgrad: EV/EBIT, lågt bäst, förlust sämst; avkastning på kapital: ROIC före skatt (närmaste mått i basdatan); båda krävs, lika vikt (percentiler i stället för rangsumma)
- parameterrum (8): antal {20, 30} × rebalansering {årlig, kvartal} × börsvärde ≥ {500 MSEK, 2 MDSEK}; ingen hysteres
- kontroll: `h0_magic_formula_universe_v1`, likavikt över samma universum med samma rebalansering

**Falsifieras om**: medianen över parameterrummet inte slår kontrollen, eller om resultatet bara håller i enstaka tidsblock.

**Resultat 2026-10-29** (trials 534–545; kontrollen 14,1–15,7 %/år, perioden börjar efter kraschen 2008):

| Rebalansering | Börsvärde | Antal | CAGR | Överavkastning mot kontroll | Block slagna |
|---|---|---|---|---|---|
| årlig | ≥ 500 MSEK | 20 | 19,2 % | +4,7 % | 62 % |
| årlig | ≥ 500 MSEK | 30 | 18,4 % | +4,0 % | 62 % |
| årlig | ≥ 2 MDSEK | 20 | 19,9 % | +4,2 % | 62 % |
| årlig | ≥ 2 MDSEK | 30 | 18,3 % | +2,5 % | 62 % |
| kvartal | ≥ 500 MSEK | 20 | 19,3 % | +5,2 % | 100 % |
| kvartal | ≥ 500 MSEK | 30 | 18,2 % | +4,0 % | 75 % |
| kvartal | ≥ 2 MDSEK | 20 | 18,6 % | +3,5 % | 88 % |
| kvartal | ≥ 2 MDSEK | 30 | 17,7 % | +2,6 % | 62 % |

Alla 8 slår kontrollen, median +4,0 %/år. Årlig rebalansering är ojämnare (svag 2013–2020); kvartalsvis jämnare. CSCV: PBO 87 % (parametervalet är brus), bästa in-sample förlorar mot kontrollen out-of-sample i 13 %; deflaterad Sharpe 97 % med H6:s 8 försök. **Status:** inte falsifierad. Reservation: formeln är nära släkt med H2 och H5 (värdering + kvalitet), så räknat över hela familjen av liknande försök är beviset svagare än 8 försök antyder.

**Andra marknader, förregistrerat 2026-10-30**: `magic_formula_{no,fi,dk,eu}_v1`, samma 8 kombinationer; omsättningsgolv som H2, börsvärdesgolv 500 M / 2 MD NOK, 50 M / 200 M EUR (Finland, Europa), 350 M / 1,4 MD DKK; kontroller `h0_magic_formula_universe_{no,fi,dk,eu}_v1` (likavikt över samma universum, samma rebalansering och golv); period 2008-12–2026.

**Resultat andra marknader 2026-10-30**: överavkastning mot kontrollen, median (min–max), konfigurationer före: SE +4,0 % (8/8), NO +4,3 % (+2,2 – +5,5, 8/8), FI +1,2 % (−0,6 – +3,3, 6/8), DK +0,1 % (−0,8 – +0,8, 5/8), EU −0,9 % (−1,8 – +1,8, 2/8). Magiska formeln håller i Sverige och Norge men inte i Danmark och Europa; svagare än H2 och värdekompositen i samma marknader.

---

## H7 — Värdekomposit

**Idé**: Ranka på flera värderingsmått samtidigt i stället för ett (som H5:s P/E): ett bolag som är billigt på många mått är mer sannolikt verkligt billigt.

**Motivering**: Sammansatta värdemått (O'Shaughnessy) har historiskt varit stabilare än enskilda mått; ett enskilt mått kan vara missvisande av redovisningsskäl.

**Förregistrering 2026-10-30**: `config/strategies/value_composite_daily_v1.yaml`, SE 2008–2026. Lika vikt på percentiler av EV/EBIT, P/E, P/B, P/S (lågt; förlust eller negativt eget kapital sämst), FCF-yield och direktavkastning (högt); data för minst 75 % av vikten. Omsättning ≥ 1 MSEK/dag, topp 25, kvartalsvis, sälj utanför rank 1,5N. Samma 18 överlägg som för H2 (timing × exit × sälj på rank); ingen timing, ingen exit och sälj på rank är vanlig värdekomposit. Kontroll `h0_liquid_equal_weight_se` (kvartal).

**Falsifieras om**: den vanliga värdekompositen inte slår kontrollen, eller bara i enstaka tidsblock.

**Resultat 2026-10-30** (trials 629–646): vanlig värdekomposit 15,1 %/år (kontrollen 9,7 %), +5,3 %/år, slår kontrollen i 7 av 8 block (svagt 2017–2019), Sharpe 0,66, största drawdown −50 %. Inte falsifierad.

Överläggen (median över övriga val, mot vanlig värdekomposit):
- **stops** lyfter både avkastning och risk: stop 20 % −0,6 %/år men Sharpe 0,58 → 0,83 och drawdown −45 % → −22 %; utan timing och med bara exits som säljer: stop 30 % 18,2 %/år (+3,1, slår referensen i 6 av 8 block), stop 20 % 16,6 % (+1,6, 7 av 8 block).
- **timing** (200 d eller utbrott) kostar ~2,3 %/år men sänker drawdown; bäst riskjusterat 200 d + stop 20 % + bara exits säljer: 14,7 %, Sharpe 0,90, drawdown −21 %.
- **behålla hårt utan exits** sämst (9,9 %/år).

Värdekompositen är den strategi där stops hjälper mest: den har störst drawdown utan dem.

**Andra marknader, förregistrerat 2026-10-30**: `value_composite_{no,fi,dk,eu}_v1`, samma regler utan timing; exit {ingen, stop 20 %, 30 %} × sälj på rank {ja, nej} = 6 per marknad (prövar också om stops hjälper värdekompositen även där); omsättningsgolv som H2 i respektive marknad; kontroll `h0_liquid_equal_weight_{no,fi,dk,eu}`.

**Resultat andra marknader 2026-10-30** (trials 671–742). Överavkastning mot likvid likavikt (kvartal), utan stop / stop 20 % (bara exits säljer) / stop 30 % (bara exits säljer):

| Marknad | Vanlig | Stop 20 % | Stop 30 % | Största drawdown utan / med stop 20 % |
|---|---|---|---|---|
| SE | +5,3 % | +6,9 % | +8,4 % | −50 % / −36 % |
| NO | +7,8 % | +9,1 % | +7,7 % | −51 % / −37 % |
| FI | +1,4 % | +2,7 % | +1,9 % | −48 % / −37 % |
| DK | +3,5 % | +6,0 % | +5,4 % | −52 % / −39 % |
| EU | +6,5 % | +9,5 % | +9,1 % | −57 % / −42 % |

Alla 30 konfigurationer slår kontrollen. Värdekompositen håller i alla fem marknader, och stops höjer avkastningen och sänker drawdown i alla fem. Utan stops och utan att sälja på rank är den svagast överallt. Den mest robusta strategin hittills.

---

## H8 — Värde/kvalitet och momentum i separata delar

**Idé**: Kör en värde- eller kvalitetsstrategi och en momentumstrategi sida vid sida med fasta andelar av kapitalet (`sleeves_v1`), ombalanserade kvartalsvis. Strategierna har haft sina bra år vid olika tidpunkter och kan komplettera varandra.

**Förregistrering 2026-10-30** (SE 2008–2026, 10 bps på flyttade pengar mellan delarna; medlemmarna är redan loggade försök):
- värdedel: vanlig H2 (`h2_daily_v1`, ingen timing, ingen exit, sälj på rank) eller vanlig värdekomposit (`value_composite_daily_v1`, samma)
- momentumdel: vanlig momentum (`momentum_daily_v1`, samma) eller momentum med utbrott 50 d + stop 20 % + bara exits säljer
- momentumandel: 30 % eller 50 %
- 2 × 2 × 2 = 8. Obs: utbrott + stop är den bästa momentumvarianten från ablationen, så den delen bär urvalsbias; vanlig momentum finns med som jämförelse.

**Bedöms** mot värdedelen ensam (förbättras Sharpe och drawdown?) och mot kontrollen `h0_liquid_equal_weight_se` (kvartal).

**Resultat 2026-10-30** (trials 663–670; nyckeltal från dagliga avkastningar):

| | CAGR | Sharpe | Största drawdown |
|---|---|---|---|
| H2 ensam | 15,2 % | 0,65 | −50 % |
| värdekomposit ensam | 15,0 % | 0,62 | −54 % |
| momentum ensam / med utbrott + stop | 10,1 % / 14,0 % | 0,36 / 0,84 | −56 % / −29 % |
| H2 + 30 % / 50 % vanlig momentum | 13,8 % / 12,8 % | 0,59 / 0,53 | −49 % / −48 % |
| H2 + 30 % / 50 % momentum med utbrott + stop | 15,0 % / 14,8 % | 0,75 / 0,81 | −42 % / −37 % |
| värdekomposit + 30 % / 50 % vanlig momentum | 13,8 % / 12,9 % | 0,58 / 0,53 | −52 % / −50 % |
| värdekomposit + 30 % / 50 % momentum med utbrott + stop | 15,0 % / 14,8 % | 0,73 / 0,80 | −46 % / −40 % |

Överavkastningarna mot kontrollen är okorrelerade (H2 mot momentum 0,04–0,11) eller negativt korrelerade (värdekomposit mot momentum −0,23 till −0,43), så delarna kompletterar varandra. Men avkastningarna i sig är starkt korrelerade (0,64–0,81, alla är svenska aktier), och vanlig momentum har för liten egen fördel: blandningen sänker avkastningen. Med momentum med utbrott + stop blir Sharpe bättre (0,75–0,81 mot 0,62–0,65) och drawdown mindre till nästan samma avkastning, men den momentumvarianten är vald i efterhand. Stops direkt på värdedelen (H7: 16–18 %/år, Sharpe ~0,8) gav liknande riskminskning med högre avkastning. **Slutsats:** delarna kompletterar varandra på papperet, men ingen tydlig vinst jämfört med en värdestrategi med stops.

---

## H9 — Trendföljning med Ichimoku

**Idé**: Köp aktier i stark trend när trenden bekräftas och sälj när den bryts, utan fundamenta. Ichimoku (molnet) som signal; kandidaterna är de med starkast 12-1-månaders momentum.

**Motivering**: Trender i enskilda aktier tenderar att fortsätta (momentum); en tydlig inträdes- och utträdesregel kan fånga trenderna och kapa krascherna som vanlig momentum drabbas av (se ablationen: utbrott + stop förbättrade momentum).

**Förregistrering 2026-10-30**: `config/strategies/trend_ichimoku_v1.yaml`, SE 2008–2026, omsättning ≥ 1 MSEK/dag, månadsvis kandidatlista = topp N efter momentum, köp när Ichimoku-signalen är på, sälj när kursen stänger under molnet (ingen försäljning på rank). Ichimoku på stängningskurser (totalavkastningsindex; varianten utan högsta/lägsta kurs). Parameterrum (4): signal {över molnet, alla fyra villkor} × antal {20, 40}. Kontroll `h0_liquid_equal_weight_monthly_v1`. Jämförs också med momentum med utbrott + stop (`momentum_daily_v1`).

**Dessutom**: `value_composite_ichimoku_v1` (H7): värdekompositen med Ichimoku-timing {ingen, över molnet, alla fyra} × sälj under molnet {nej, ja} (6), jämförs med 200-dagars medel och utbrott i den tidigare ablationen.

**Falsifieras om**: trendsystemet inte slår kontrollen, eller bara i enstaka tidsblock.

---

## Överlägg som testas på alla hypoteser (stadium 4)

**Timing och exits på H2, förregistrerat 2026-10-29** (`config/strategies/h2_daily_v1.yaml`): H2 v1 med lika vikt, 25 innehav, kvartalsvis, SE 2008–2026, plus den dagliga klockan. Parameterrum (18): timing {ingen, pris över 200-dagars medel, 50-dagars utbrott} × exit {ingen, trailing stop 20 %, 30 %} × sälj på rank {ja, nej (bara exits säljer)}. Ingen timing, ingen exit och sälj på rank är vanlig H2 (referens). Jämförs med referensen och med kontrollen `h0_liquid_equal_weight_se` (kvartal) på avkastning, Sharpe och största drawdown. Ett överlägg bedöms tillföra något om det förbättrar riskjusterad avkastning eller drawdown mot referensen i de flesta kombinationer och i de flesta tidsblock, inte i en enda.

**Resultat 2026-10-30** (trials 560–591; 16 körningar misslyckades först på grund av för litet delat minne i databasens container och kördes om): referensen (vanlig H2) 15,3 %/år, Sharpe 0,71, största drawdown −44 %.

| Överlägg (median över övriga val) | Avkastning mot referensen | Sharpe | Största drawdown | Block där det slår referensen |
|---|---|---|---|---|
| timing: ingen | −0,1 % | 0,74 | −40 % | 38 % |
| timing: över 200-dagars medel | −2,5 % | 0,75 | −26 % | 31 % |
| timing: 50-dagars utbrott | −3,6 % | 0,66 | −27 % | 31 % |
| exit: ingen | −3,6 % | 0,60 | −41 % | 31 % |
| exit: trailing stop 20 % | −2,2 % | 0,77 | −22 % | 38 % |
| exit: trailing stop 30 % | −2,5 % | 0,73 | −28 % | 38 % |

- **Trailing stop utan timing** är det enda som höjer avkastningen: stop 20 % och bara exits säljer: 16,0 %/år (+0,7), Sharpe 0,78, drawdown −35 %, slår referensen i 5 av 8 block. Stop 30 %: +0,4 %.
- **Timing** (200-dagars medel eller utbrott) kostar 2,5–3,6 %/år i avkastning men halverar ungefär drawdown; riskjusterat ungefär oförändrat (200 dagar) eller sämre (utbrott). Lägst risk: 200-dagars medel + stop 20 % + sälj på rank: 12,1 %/år, Sharpe 0,83, drawdown −18 %.
- **Behålla hårt utan exits** (aldrig sälja på rank) är sämst: 10,7 %/år: H2:s rankning behöver få sälja.
- Alla 18 slår kontrollen (likavikt över samma likvida universum), +0,9 till +6,2 %/år.

**Slutsats:** exits (trailing stops) och timing är framför allt riskreducerare, inte avkastningshöjare: drawdown sjunker kraftigt i alla kombinationer med stop, Sharpe förbättras i de flesta, men avkastningen mot vanlig H2 är lägre i de flesta tidsblock. Kriteriet (bättre riskjusterat eller drawdown i de flesta kombinationer och block) uppfylls för drawdown men inte för avkastning per block. 18 nya försök för H2 (nu 306).

**Samma överlägg på momentum och magiska formeln, förregistrerat 2026-10-30**: samma 18 kombinationer (timing × exit × sälj på rank) på
- `momentum_daily_v1` (H5): 12-1-månaders momentum, topp 30, månadsvis, omsättning ≥ 1 MSEK/dag (H5 hade inget likviditetsgolv; här för jämförbarhet med kontrollen och handelbarhet), 2008–2026, kontroll `h0_liquid_equal_weight_monthly_v1` (likavikt över samma likvida universum, månadsvis).
- `magic_formula_daily_v1` (H6): magiska formeln, topp 20, kvartalsvis, börsvärde ≥ 500 MSEK, 2008-12–2026, kontroll `h0_magic_formula_universe_v1` (kvartal, ≥ 500 MSEK).

Samma bedömning som för H2. Frågan: hjälper stops och timing momentum (känd för plötsliga krascher) mer än kvalitets- och värdestrategierna?

**Resultat 2026-10-30** (trials 592–628; kontrollen månadsvis likavikt 9,5 %/år):

| | Referens (vanlig) | Bästa riskjusterade | Timing, median mot referens | Stops, median mot referens |
|---|---|---|---|---|
| Momentum (H5) | 10,1 %/år, Sharpe 0,44, drawdown −53 % | utbrott 50 d + stop 20 % + bara exits säljer: 14,0 %, Sharpe 0,80, −26 % | utbrott: +0,9 %/år, Sharpe 0,69, drawdown −28 %, slår referensen i 5 av 8 block; 200 d: ±0 | ±0, drawdown oförändrad eller sämre utan timing |
| Magiska formeln (H6) | 19,3 %/år, Sharpe 0,90, drawdown −27 % | stop 20 % + sälj på rank: 18,8 %, Sharpe 0,95, −22 % | −4,7 till −5,3 %/år, Sharpe ~0,85, slår referensen i 1–2 av 8 block | −0,4 till −1,6 %/år, drawdown −22 till −25 % |

**Slutsats över H2, momentum och magiska formeln:**
- **Timing som inträdesfilter** kostar avkastning för kvalitets- och värdestrategier (H2 −2,5 till −3,6 %/år, magiska formeln ~−5 %/år): billiga bolag köps ofta innan trenden vänt, och det är där avkastningen finns. Drawdown minskar.
- **Momentum gynnas av utbrottstiming**, konsekvent över kombinationerna: Sharpe 0,44 → ~0,69, drawdown −53 % → ~−28 %. Utbrott bekräftar momentum; 200-dagars medel gör det inte.
- **Trailing stops** är milda riskreducerare för kvalitet och värde (ungefär oförändrad avkastning, lägre drawdown), men hjälper inte momentum utan timing.
- **Behålla hårt utan exits** är sämst i alla tre.
- Momentum på det likvida universumet slår kontrollen knappt (+0,6 %/år) utan överlägg. Försöken räknas: H5 +18, H6 +18.


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
