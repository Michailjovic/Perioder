# Perioder — analýza projektu a roadmapa

Vlastní Home Assistant custom component pro řízení menstruačního cyklu a antikoncepce. Inspirace integrací [cyclist](https://github.com/ringleader/cyclist), ale píšeme si vlastní komponentu od nuly. Cílem je **obecná integrace** — ne řešení na míru jedné domácnosti, ale nástroj, který si nastaví a použije kdokoli s podobnou potřebou (jednotlivec, pár, širší podpůrná síť).

> Toto je nástroj domácí automatizace, ne zdravotnický nástroj. Kalendářní predikce plodnosti mají nízkou přesnost bez fyziologických dat. Nenahrazuje konzultaci s gynekologem.

---

## 1. Cíl a filozofie

- **Lokální a soukromé** — vše v `.storage/` HA instance, žádný cloud, žádná externí appka.
- **Obecně použitelné, bez předpokladu monogamního páru** — jeden config entry = jeden "vlastník cyklu" (osoba, jejíž cyklus se sleduje). K ní se váže libovolný počet "podporovatelů" (partner, partnerka, spolubydlící, rodič, kdokoli) — s tím, co a jak kdo dostává, rozhoduje administrátor HA instance (viz 2.5), ne sám vlastník cyklu. Vztah vlastník cyklu ↔ podporovatel je **N:M a neomezený oběma směry**: jeden podporovatel se může přihlásit k odběru u libovolného počtu vlastníků cyklu (polyamorní vztahy, více partnerek najednou) a jeden vlastník cyklu může mít libovolný počet podporovatelů. Nic v datovém modelu ani UI nepředpokládá pár, manželství ani konkrétní pohlaví/roli — jen "vlastník cyklu" a "podporovatel", a jedna osoba může být v jiném config entry zároveň jedním i druhým. Žádné jméno ani vztahová role není zadrátovaná v kódu.
- **Počet sledovaných osob je neomezený** — HA integrace přirozeně podporuje víc config entries stejné domény, takže jedna instance může mít libovolný počet nezávislých "vlastníků cyklu" současně, každý se svým vlastním nastavením a okruhem podporovatelů.
- **Cíl trackování je nastavitelný** — `track` / `avoid` / `plan`, kdykoli přepnutelné, notifikace se tomu přizpůsobí.
- **Jeden zdroj pravdy** — zápis prvního dne menstruace (dashboard, tlačítko, hlas, NFC) je jediná věc, kterou vlastník cyklu aktivně zadává pravidelně. Od tohoto data se odvozuje úplně vše ostatní: den cyklu, fáze, plodnost, PMS okno, predikce.
- **Antikoncepce jako samostatný, ale propojený modul** — nezávisí na cyklu 1:1 (balení má vlastní rytmus), ale prolíná se s ním tam, kde to má smysl (vynechaná dávka ve fertilním okně = varování navíc).

---

## 2. Funkční okruhy

### 2.1 Cyklus a plodnost (základ z cyclist)

- Datum posledního začátku periody → odvozený den cyklu, fáze (menstruace/folikulární/ovulace/luteální), plodnost (`fertile`/`low`/`safer`).
- Nastavitelná `cycle_length` a `period_duration`, žádné dopočítávání z historie ve výchozím stavu — nastavení má přednost.
- Volitelně navíc BBT/CM/LH pro symptothermální zpřesnění (pozdější fáze, není nutné pro MVP).
- Kalendář (`calendar.perioder`) s výhledem 3 měsíce dopředu — perioda + fertilní okno.
- ✅ **(nápad z 2026-07-29, implementováno v0.3.0)** Kalendář zobrazuje historii antikoncepce po dnech — kdy byl prášek potvrzeně vzatý/vynechaný (`pill_log`), a v popisu události i míru zpoždění oproti `reminder_time` (v minutách). Nezobrazují se odhady za budoucí/nezalogované dny, jen skutečně zalogované záznamy.
- Cíl (`goal`) ovlivňuje tón a typ notifikací.

### 2.2 PMS / emoční okno

- Odvozené okno na konci luteální fáze — posledních `pms_window_days` dní před predikovanou periodou (nastavitelné, default např. 4).
- **Ruční přebití per cyklus** — vlastník cyklu může pro aktuální cyklus okno explicitně zapnout nebo vypnout (`perioder.set_pms_override` s hodnotou `true`/`false`/`null` = zpět na automatiku), protože to nemusí platit každý měsíc stejně.
- `binary_sensor.perioder_pms_aktivni` — `on` v tomto okně (po zohlednění případného přebití).
- Notifikace podporovatelům je vždy volitelná a **konfigurovatelná per příjemce** (viz 2.5) — obecná ("blíží se náročnější dny, buď ohleduplný") nebo detailnější, pokud si to příjemce i vlastník cyklu vyžádají.
- **Výhradně pro podporovatele** — karta/notifikace PMS okna se nezobrazuje na dashboardu vlastníka cyklu (ta ho sama nepotřebuje, zná svůj stav bez upozorňování), je to údaj určený výhradně pro okolí, které si o něj řeklo. Viditelnost je řízená čistě odběrem dané kategorie u konkrétního podporovatele (viz 2.5) — nikdy podle pohlaví nebo role, tyhle atributy systém vůbec neřeší.

### 2.3 Antikoncepce — řízení a připomínky

- `active` (zapnuto/vypnuto bez mazání historie), `regimen_type` (`21_7`, `24_4`, `continuous`, `custom`), `pack_start_date`, `reminder_time`, `pill_log`.
- `is_pill_day = active AND day_in_pack < pack_size` — čistá funkce, žádné HA závislosti.
- Denní připomínka jen když je dnes skutečně den na prášek a ještě nepotvrzeno; actionable notifikace s tlačítkem "Vzato"; eskalace při nepotvrzení (nastavitelný interval a počet opakování); ticho o víkendu... teda o pauze balení a při `active = false`.
- Vynechaná dávka → záznam `missed`, ranní souhrn vlastníkovi cyklu i přihlášeným podporovatelům.
- Propojení s plodností: pokud vynechaná dávka spadne do fertilního okna, notifikace explicitně upozorní na potřebu záložní ochrany.
- Docházející balení → notifikace na dokoupení (nastavitelný počet dní předem).
- Služby: `start_new_pack`, `set_contraception_active`.

### 2.4 Symptomy a historie/trendy

- Rozšířený log symptomů (nálada, křeče, bolest hlavy, energie, ...) s časovou značkou — `perioder.log_symptom`.
- Historie umožňuje: zpětně vidět vzorec v konkrétním cyklu, dashboard graf (history/statistics graph card), a v budoucnu i zpřesnění PMS okna na základě reálných dat místo pevného počtu dní.
- Exportovatelný log (např. do CSV) pro potřeby konzultace s gynekologem.

### 2.5 Notifikace a "podporovatelé"

- **Oprávnění nastavuje administrátor HA instance, ne vlastník cyklu.** Config Flow a Options Flow jsou v Home Assistantu beztak přístupné jen uživatelům s administrátorským právem (běžný uživatel se do Nastavení > Zařízení a služby vůbec nedostane), takže tohle jen odpovídá realitě platformy — a zároveň je to vědomé rozhodnutí: administrátor je ten, kdo zná celou domácnost/skupinu a nejlépe posoudí, kdo má co dostávat, bez nutnosti schvalovacího kroku od vlastníka cyklu.
- Administrátor v Options Flow přidává libovolný počet podporovatelů k libovolnému vlastníkovi cyklu, kterého v instanci spravuje. Stejná osoba (stejný `mobile_app_*` cíl) se může objevit jako podporovatel u více různých vlastníků cyklu zároveň — nastavení odběru je vždy vázané na konkrétní **dvojici** (vlastník cyklu, podporovatel), ne globálně na osobu. U každé takové dvojice se nastaví:
  - notifikační cíl (`mobile_app_*` zařízení),
  - kategorie, které daný podporovatel odebírá (PMS okno, blížící se perioda, docházející balení, vynechaná dávka, fertilita/plodnost),
  - úroveň detailu (obecná vs. s detailem symptomů).
- Vlastník cyklu vždy vidí vše za sebe na svém dashboardu; podporovatelé jen to, co jim administrátor nakonfiguroval, a jen za toho vlastníka cyklu, u kterého jsou přihlášeni.
- Vzor s `tag` (proti hromadění) a skupinou podle typu (`antikoncepce`, `cyklus`, `pms`), navíc odlišené podle vlastníka cyklu, aby se notifikace od více sledovaných osob nepletly dohromady.

### 2.6 Komfortní automatizace (blueprinty nad integrací)

- Scéna osvětlení / "nerušit" návrh během periody nebo PMS okna.
- Připomínka ohřívacího polštářku.
- Automatické přidání položek do HA nákupního seznamu (`todo.add_item`) při docházející antikoncepci nebo blížící se periodě.
- Toto jsou samostatné blueprinty (jako `BLUEPRINTS.md` v cyclist), ne jádro integrace — uživatel si je zapíná dobrovolně.

### 2.7 Sdílený kalendář s úrovní soukromí

- `calendar.perioder` — detailní, jen pro vlastníka cyklu.
- `calendar.perioder_shared` — generické bloky ("citlivé období") bez detailu, viditelné/exportovatelné do sdíleného rodinného kalendáře. Vlastník cyklu volí, které kategorie se do sdíleného kalendáře vůbec promítnou.

### 2.8 Vacation / pauza režim

- Jedno tlačítko/služba `perioder.pause_notifications` (volitelně s datem obnovení) — dočasně ztiší úplně všechny notifikace všem podporovatelům, bez nutnosti měnit nastavení jednotlivých modulů. Podkladová data (cyklus, antikoncepce) se dál počítají a logují, jen se o tom nikdo neobtěžuje notifikacemi.

### 2.9 Dashboard

- Karta stavu cyklu (den, fáze, gauge), stavu antikoncepce (dnešní stav, dní do konce balení), PMS okna.
- Rychlé akce: "Perioda začala", "Prášek vzat", log symptomu.
- Kalendářová karta (detailní i sdílená verze).
- Přehled podporovatelů a jejich nastavení odběru.
- Karta PMS okna se zobrazuje jen v pohledu podporovatele (dashboardu/notifikaci), ne v pohledu vlastníka cyklu (viz 2.2).
- **Agregovaný pohled pro podporovatele** — pokud jedna osoba podporuje víc vlastníků cyklu najednou (např. v polyamorním vztahu), samostatná karta/dashboard, která ukáže stav za všechny sledované osoby vedle sebe, ne jen jednu.

---

## 3. Entity (návrh)

| Entita | Popis |
|---|---|
| `sensor.perioder_cyklus_den` | Aktuální den cyklu |
| `sensor.perioder_faze` | `menstruace`/`folikularni`/`ovulace`/`luteal` |
| `sensor.perioder_plodnost` | `fertile`/`low`/`safer` |
| `sensor.perioder_dalsi_perioda` | Dní do predikované periody |
| `binary_sensor.perioder_perioda_aktivni` | `on` během periody |
| `binary_sensor.perioder_pms_aktivni` | `on` v PMS okně (po zohlednění ručního přebití) |
| `sensor.perioder_antikoncepce_stav` | `vzato`/`ceka_se`/`pauza`/`neaktivni`/`vynechano` |
| `binary_sensor.perioder_pilulka_dnes_potreba` | `on` když je dnes den na prášek a ještě nepotvrzeno |
| `sensor.perioder_antikoncepce_zbyva_dni` | Dní do konce balení |
| `calendar.perioder` | Detailní predikce cyklu + rozvrh balení |
| `calendar.perioder_shared` | Generické bloky pro sdílený kalendář |

## 4. Služby (návrh)

| Služba | Popis |
|---|---|
| `perioder.log_period_start` | Start periody, volitelný `date:` |
| `perioder.log_pill_taken` | Potvrzení užití prášku, volitelný `date:` |
| `perioder.start_new_pack` | Start nového balení, volitelný `regimen_type:` |
| `perioder.set_contraception_active` | Zapnout/vypnout užívání (bez mazání historie) |
| `perioder.set_pms_override` | Ruční přebití PMS okna pro aktuální cyklus (`true`/`false`/`null`) |
| `perioder.log_symptom` | Log symptomu s časovou značkou |
| `perioder.pause_notifications` | Dočasné ztišení všech notifikací, volitelné datum obnovení |
| `perioder.update_settings` | `cycle_length`, `period_duration`, `goal`, `reminder_time`, `pms_window_days` |

---

## 5. Technická architektura

- `custom_components/perioder/` — vlastní HA integrace, `DOMAIN = "perioder"`. Jeden config entry = jeden vlastník cyklu; instance HA jich může mít libovolný počet bez umělého omezení.
- Config Flow (vlastník cyklu + základní nastavení) + Options Flow (úprava nastavení + správa podporovatelů a jejich odběrů, N:M vůči ostatním entries).
- **Nastavení a podporovatelé žijí v config entry** (`data`/`options`), ne ve Store — spravuje je Config/Options Flow a čte `settings.py`. Runtime `Store` (`hass.helpers.storage.Store`, JSON) drží jen to, co se mění službami mezi úpravami nastavení: `last_period_start`, `pms_override`, `contraception` (aktivní balení, log pilulek), `symptoms`/`symptom_log` — vždy pod konkrétním config entry, tedy pod konkrétním vlastníkem cyklu. Rozdělení zabraňuje rozjetí dvou kopií téže věci (v0.1.0 to původně mělo duplicitně i ve Store, opraveno před prvním pushem).
- Čistá výpočetní logika oddělená od HA (`cycle_math.py`, `pill_math.py`) — testovatelné bez HA runtime.
- Distribuce přes HACS (custom repository).
- Eskalace připomínek přes `timer.*` helpery + reakce na `mobile_app_notification_action`, ne přes opakované automatizace navázané na fixní čas.
- **Backend vs. frontend, verzování:** Python kód v `custom_components/perioder/` je backend, jen běží uvnitř procesu Home Assistanta (žádný samostatný server). Pro **v1.x** stačí jeden HACS repozitář (kategorie Integration) — dashboard se skládá ze standardních vestavěných Lovelace karet, žádná vlastní frontend karta se nepíše. Vlastní JS Lovelace karta (hezčí vizualizace typu gauge) je odložená na **v2.0.0** — buď přibalená do stejného repozitáře (integrace si zaregistruje vlastní Lovelace resource sama), nebo jako samostatný HACS "Plugin" repozitář, pokud by dávalo smysl použití i mimo tuto integraci. Rozhodnutí které varianty padne až při plánování v2.0.0.

## 6. Bezpečnost a soukromí

- Žádná data neopouští HA instanci.
- Podporovatelé vidí jen to, na co mají svolení (per-kategorie, per-detail úroveň) — nikdy víc, dokud to administrátor nepovolí (viz 2.5).
- Jasný disclaimer v README, že jde o domácí automatizaci, ne zdravotnický nástroj.

---

## 7. Roadmapa

### M0 — Rozhodnutí a specifikace (tento dokument)
- [x] Analýza funkcí a ovládání
- [x] Zvolen vlastní custom component od nuly, obecně použitelný (ne na míru jedné domácnosti)
- [x] Rozšíření o PMS okno, symptomy/trendy, komfortní automatizace, sdílený kalendář, pauza režim

### M1 — Základ projektu ✅ (v0.1.0)
- [x] `manifest.json`, `const.py`, `hacs.json`
- [x] Config Flow: cycle_length, period_duration, goal, regimen_type, reminder_time, pms_window_days
- [x] Options Flow: úprava nastavení + správa podporovatelů (přidání/odebrání, kategorie, detail úroveň)
- [x] Storage layer (`cycle`, `contraception`, `symptoms`, `supporters`)
- [x] `cycle_math.py`

**Poznámka:** v0.1.0 zároveň natáhla dopředu část M3 (viz níže), aby šlo hned něco reálně vidět na dashboardu s testovacími daty — čistě M1 (bez entit) by samo o sobě nebylo testovatelné.

### M2 — Antikoncepční jádro ✅ z části (v0.2.0)
- [x] `pill_math.py`: is_pill_day, zbývající dny balení, stav dne (`pill_status`)
- [x] `sensor.py` + `binary_sensor.py` pro antikoncepci, `button.py` (potvrzení jedním klikem)
- [x] Služby: `log_pill_taken`, `start_new_pack`, `set_contraception_active`
- [ ] Denní připomínka + eskalace (timer helper + actionable notification) — přesunuto k M4, sdílí infrastrukturu s podporovatelským notifikačním enginem (viz CHANGELOG v0.2.0)
- [ ] Ranní "vynecháno" souhrn + propojení s fertilním oknem — bude řešeno spolu s M4

### M3 — Cyklus, plodnost a PMS okno ✅ (v0.3.0)
- [x] `sensor.py`: cycle_day, phase, fertility, next_period
- [x] `binary_sensor.py`: period_active, pms_active (s ručním přebitím)
- [x] Služby: `log_period_start`, `set_pms_override`
- [x] `calendar.py` — predikce period/plodných dní/pauz balení (dopředu i zpětně), plus zobrazení logovaných `pill_log` záznamů (vzato/vynecháno) s výpočtem zpoždění oproti `reminder_time` (nápad z 2026-07-29, viz 2.1 a CHANGELOG v0.3.0)
- [x] Služba: `update_settings`

### M4 — Podporovatelé a notifikace ✅ z části (v0.4.0)
- [x] Datový model podporovatelů (cíl, kategorie, detail úroveň) — hotovo už v Options Flow (v0.1.1)
- [x] Notifikační engine respektující odběry a úroveň detailu per příjemce (`notifications.py`)
- [x] Denní připomínka antikoncepce + eskalace (přesunuto z M2 — viz CHANGELOG v0.2.0/v0.4.0), včetně "vynecháno" notifikace a propojení s fertilním oknem — informační notifikace, zatím BEZ actionable tlačítka přímo v notifikaci (potvrzení stále přes dashboard/tlačítko/službu, ne přímou akcí z push notifikace)
- [x] `perioder.pause_notifications` + `switch.pause_notifications`
- [ ] **Nedokončeno, vědomě odloženo:** `pms`/`period`/`fertility` jako vlastní *transition-triggered* notifikace podporovatelům (např. "právě začalo PMS okno", "perioda za 2 dny") — odběry těchto kategorií existují od v0.1.1, dispatch engine z v0.4.0 už to umí odbavit, jen zatím nic tyhle 3 kategorie nespouští
- [ ] Actionable notifikace (tlačítko "Vzato" přímo v push notifikaci, ne jen na dashboardu) — vyžaduje naslouchání HA události `mobile_app_notification_action`, zatím neimplementováno
- [ ] Ověření proti reálné běžící Home Assistant instanci a reálnému mobile_app zařízení — zatím ověřeno jen logikou (standalone simulace rozhodovacího stromu), ne živým doručením notifikace

### M5 — Symptomy, sdílený kalendář, dashboard ✅ (v0.5.0)
- [x] `log_symptom` (služba + tlačítka per symptom) + `sensor.last_symptom`; export přes `perioder.export_symptom_log` (CSV do `www/`)
- [x] `calendar.*_shared_calendar` s generickými bloky, kategorie voleny přes `shared_calendar_categories`
- [x] Dashboard karty (cyklus, antikoncepce, PMS, podporovatelé přes `sensor.supporters`, rychlé akce včetně symptomů)
- [ ] Grafy historie/trendů (history/statistics graph card) — `sensor.last_symptom` a `sensor.contraception_status` už mají potřebná data, ale žádná konkrétní graf-karta zatím není součástí `dashboard_test.yaml`
- [ ] Učení PMS okna ze symptomové historie (zmíněno jako budoucí možnost v 2.4, ne součást M5)

### M6 — Blueprinty a komfortní automatizace ✅ (v0.6.0)
- [x] Blueprint: osvětlení/scéna v periodě/PMS okně (`period_pms_lighting_scene.yaml`)
- [x] Blueprint: nákupní seznam při docházející antikoncepci/periodě (`contraception_period_shopping_list.yaml`)
- [x] Blueprint: připomínka ohřívacího polštářku (`heating_pad_reminder.yaml`)
- Viz `BLUEPRINTS.md` pro import a popis; ověřeno jen staticky (konzistence `!input` vs deklarované vstupy), ne živým importem do běžící instance

### M7 — Polish, testy a GitHub dokumentace (uzavírá v1.0.0)
- [ ] `tests/test_pill_math.py`, `tests/test_cycle_math.py`
- [ ] Edge cases: změna regimen_type uprostřed balení, vysazení a opětovné zapnutí, zpětné logování, budoucí datum (odmítnout), PMS override napříč cykly
- [ ] `README.md`: instalace (HACS + manuál), first-use postup, popis modelu vlastník cyklu/podporovatel/administrátor, příklady automatizací a blueprintů, disclaimer
- [ ] `hacs.json`, GitHub Actions (`hassfest`, `hacs` validace) — stejně jako u cyclist
- [ ] `CHANGELOG.md` se semver — v1.0.0 = tento rozsah, bez vlastní frontend karty
- [ ] Screenshoty dashboardu do README

### v2.0.0 — Budoucí rozšíření (mimo současný rozsah)
- [ ] Vlastní Lovelace karta (JS) — gauge/vizualizace na míru místo standardních karet
- [ ] Rozhodnutí: přibalit do repozitáře integrace, nebo vydat jako samostatný HACS frontend "Plugin"
- [ ] Volitelné: učení PMS okna ze symptomové historie místo pevného nastavení (viz otevřené otázky)

---

## 8. Verzování a release proces

- **Semver od v0.1.0**: `MAJOR.MINOR.PATCH`. MAJOR = zásadní/nekompatibilní změna, MINOR = nová funkčnost v rámci daného major (typicky = dokončení jednoho milníku), PATCH = oprava chyby bez nové funkčnosti.
- **Tři fáze podle rozsahu verzí:**

  | Rozsah | Fáze | Charakter |
  |---|---|---|
  | v0.1.0 – v0.x.x | Alfa vývoj | Postupné minor verze zhruba podle milníků M1–M7, ale rozsah i pořadí se může měnit — funkce se ještě dolaďují, nic není finální. |
  | v1.0.0 | Odsouhlasený produkt | Bod, kdy společně potvrdíme, že funkční rozsah (M1–M7: cyklus, antikoncepce, PMS, podporovatelé, symptomy, blueprinty, testy, dokumentace) je hotový a použitelný — ne nutně totožné s "M7 dokončeno" na den přesně, ale okamžik shody. |
  | v1.x.x – v2.0.0 | Stabilní použití + doladění | Produkt je plně použitelný a nasazený, další minor/patch verze řeší věci zjištěné za provozu i drobná rozšíření, směřuje se k vlastní frontend kartě. |
  | v2.0.0 | Frontend a další vývoj | Vlastní Lovelace karta (viz sekce 5) a pokračování podle toho, co se do té doby ukáže jako potřebné. |

  V rámci alfy (0.x) i pozdějších fází platí stejné pravidlo pro PATCH: oprava beze změny funkčnosti bumpuje jen poslední číslo (v0.1.1, v1.2.1...).

- **Release proces pro každou verzi** — cíl: od pushnutí na GitHub jde rovnou nainstalovat přes HACS bez dalšího zásahu:
  1. `version` v `manifest.json` nastavená přesně na verzi, která jde do tagu/release.
  2. `hacs.json` a GitHub Actions (`hassfest`, HACS validace — stejné jako u cyclist) musí projít bez chyby ještě před release.
  3. Pro danou verzi připravím `CHANGELOG.md` záznam v angličtině, formát Keep a Changelog (`Added` / `Changed` / `Fixed` / `Removed`).
  4. Ty commitneš, vytvoříš git tag a GitHub Release se stejným číslem, do release notes vložíš připravený changelog.
  5. V HA: přidání/aktualizace přes HACS, restart — žádný ruční zásah do kódu po instalaci.

---

## 9. Otevřené otázky

- Jaký `regimen_type` je výchozí/nejběžnější (21/7, 24/4, jiný)?
- Kolik minut/opakování eskalace připomínky antikoncepce než se přestane otravovat?
- Fyzické tlačítko/NFC v koupelně pro logování — od M2, nebo později?
- Má se PMS okno v budoucnu (M6+) učit ze symptomové historie místo pevného počtu dní, nebo zůstat čistě nastavitelné + ruční přebití?
- Vyřešeno: počet vlastníků cyklu i podporovatelů je neomezený a vztah mezi nimi je N:M — žádný předpoklad monogamního páru (viz sekce 1, 2.5, 2.9).
