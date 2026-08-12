# ADR-1: Vlastní Lovelace kalendářová karta pro Perioder

**Status:** Accepted, implementováno v0.9.30 (2026-08-13) - viz Akční kroky níže
**Datum:** 2026-08-12
**Rozhoduje:** Michael (jediný správce projektu)
**Navazuje na:** ANALYZA-A-ROADMAP.md sekce 5 ("Vlastní JS Lovelace karta...
je odložená na v2.0.0 - buď přibalená do stejného repozitáře..., nebo jako
samostatný HACS 'Plugin'... Rozhodnutí které varianty padne až při plánování
v2.0.0.") a sekce 8 (verzovací tabulka, řádek v2.0.0).

## Kontext

Perioder dnes staví kalendářový dashboard na vestavěné HA kartě
`type: calendar` (viz `calendar.py`, šest/sedm entit rozdělených po
kategoriích - `period_calendar`/`fertile_calendar`/`pms_calendar`/
`pause_calendar`/`pill_calendar`/`cycle_calendar`/`shared_calendar`). Tahle
karta má dvě reálné, dlouhodobě neřešitelné bolesti:

1. **Barvy nejdou pevně přiřadit** - HA je přiřazuje automaticky podle
   pořadí entit v kartě, ne podle toho, co entita je. Potvrzeno jako
   otevřený, dlouhodobě neřešený požadavek na straně Home Assistant samotného
   (`color` dosud není vlastnost `CalendarEntity` - viz
   [home-assistant/architecture#883](https://github.com/home-assistant/architecture/discussions/883),
   [home-assistant/frontend#11262](https://github.com/home-assistant/frontend/discussions/11262)),
   ne mezera v Perioder.
2. **Přeplněný den schová událost za "+n more"** - FullCalendar (co karta
   pod kapotou používá) řadí v jednom dni delší (víc-denní) události před
   kratší, takže jednodenní tabletková událost prohrává, i když ji chceme
   vidět nejvíc. Dnešní obchvat (`calendar_calendar` split na
   `pill_calendar`, viz v0.9.28 v CHANGELOGu) to řeší jen částečně - funguje
   jen když si uživatel ručně vypne blokové kalendáře checkboxem.

Zkoušeli jsme dvě třetí-stranové HACS karty jako náhradu:

- **`calendar-card-pro`** ([alexpfau/calendar-card-pro](https://github.com/alexpfau/calendar-card-pro))
  - není měsíční mřížka vůbec, je to agenda/seznam nadcházejících dní
    ("displaying upcoming events" - vlastní popis autora). Špatný fit, jiný
    vizuální paradigma než chceme.
- **`atomic-calendar-revive`** ([totaldebug/atomic-calendar-revive](https://github.com/totaldebug/atomic-calendar-revive))
  - má měsíční mřížku i pevné barvy per entita, ale **živě vyzkoušeno
    (2026-08-12) a nespojuje víc-denní události do jednoho pruhu** - přesně
    to, co u periody/plodného okna/pauzy potřebujeme. Nepoužitelné.

Obě navíc nesou riziko, které projektu vlastní - Perioder je zdravotní
nástroj, který v domácnosti používá i netechnický člověk (Alina); závislost
na tom, jestli je zrovna nainstalovaná/aktuální verze cizí HACS karty, a
jestli ji autor nerozbije v nějaké budoucí verzi, je zbytečné riziko navíc
oproti tomu, co si Perioder může garantovat sám.

## Rozhodnutí

Postavit vlastní Lovelace kartu `custom:perioder-calendar-card`, **přibalenou
přímo do repozitáře Perioder integrace** (ne samostatný HACS "Plugin" -
rozhodnuto v konverzaci 2026-08-12, viz "Zvažované varianty" níže), verzovanou
společně s `manifest.json`, a **automaticky registrovanou jako Lovelace
resource** při startu HA - žádný ruční krok "přidat resource" navíc k
dnešnímu setupu (`dashboard_alina.yaml` apod. se jen přepíšou na novou kartu).

## Zvažované varianty

### A. Hand-rolled měsíční mřížka (doporučeno)

Vlastní CSS grid (7 sloupců × N řádků podle měsíce), vlastní datová logika v
JS (obdoba toho, co `calendar.py`/`cycle_math.py` už dělá v Pythonu - žádná
nová backendová logika, karta jen čte hotové `calendar.*` entity). Víc-denní
bloky jako absolutně pozicované pruhy přes rozsah sloupců, rozdělené na
segmenty po týdnech tam, kde přesahují přes konec řádku (stejná technika,
jakou interně používá FullCalendar). Tabletková ikona se nikdy nepočítá do
"kolik událostí se vejde do buňky" - vykresluje se jako malý fixní badge v
rohu dne, mimo běžný event-stack.

| Kritérium | Hodnocení |
|---|---|
| Rozsah kódu | Malý - žádné závislosti, žádný build krok (viz níže) |
| Riziko | Vlastní edge-case pokrytí (přechody měsíců/roků, dnešní datum, mobil) - žádná knihovna to nepohlídá za nás |
| Kontrola nad chováním | Plná - pevné barvy i "tabletka nikdy nezmizí" jde vynutit přímo |
| Údržba | Jedna nová oblast (JS) vedle Pythonu, ale malá |

**Pros:** přesně to, co potřebujeme, nic navíc; žádná cizí závislost; malý
soubor.
**Cons:** datumovou/grid logiku, co jinde řeší FullCalendar, píšeme sami.

### B. Vendorovat/ořezat FullCalendar

Použít stejnou knihovnu, co pod kapotou používá vestavěná karta, ale
zabalenou vlastní obálkou s pevnými barvami.

**Pros:** víc-denní spanning "zadarmo", battle-tested.
**Cons:** ~100-300 kB i ořezaná; pevné barvy a prioritu tabletky bychom
stejně museli hackovat přes její API/CSS - řeší se tím přesně ten problém,
kvůli kterému od vestavěné karty odcházíme, jen v jiném balení. **Zamítnuto.**

### C. Obecná, na Perioder nezávislá kalendářová karta (vlastní HACS "Plugin")

Publikovat kartu jako samostatně instalovatelný, obecně použitelný produkt
(ne vázaný na Perioder entity).

**Pros:** potenciálně užitečné i pro jiné, mohlo by se to hodit i mimo tenhle
projekt.
**Cons:** o dost víc práce (obecné API, dokumentace, support surface, dva
release cykly k synchronizaci) - a hlavně: `Michael`ova vlastní úvaha, proč
tohle vůbec děláme ("lidé by si instalovali různé kalendáře a to by
generovalo různé bugy"), platí stejně i o *téhle* kartě, kdyby byla
samostatná. Staví to přesně na to, čemu se chceme vyhnout. **Zamítnuto,
rozhodnuto v konverzaci 2026-08-12.**

## Návrh konfigurace a chování (rozsah v1 - minimální)

```yaml
type: custom:perioder-calendar-card
title: Kalendář cyklu
entities:
  - entity: calendar.alina_period_calendar
    color: "#e05c5c"
  - entity: calendar.alina_fertile_calendar
    color: "#4a90d9"
  - entity: calendar.alina_pause_calendar
    color: "#9b59b6"
  - entity: calendar.alina_pms_calendar
    color: "#f5a623"
pill_entity: calendar.alina_pill_calendar
```

- `color` je volitelný override - bez něj karta použije vlastní výchozí
  paletu podle `translation_key` dané Perioder calendar entity (period =
  červená, fertile = modrá, pause = fialová, pms = oranžová), takže i bez
  jediného řádku konfigurace to hned vypadá rozumně a smysluplně barevně
  odlišené.
- `pill_entity`: volitelný speciální slot. Jeho eventy se **nikdy**
  nepočítají do limitu "kolik se vejde do buňky dne" - vždy je vidět jako
  malá 💊 ikonka, bez ohledu na to, kolik dalších bloků ten den má. Tohle
  přímo řeší dnešní "+n more" problém, u kořene, ne obchvatem přes
  samostatnou entitu + ruční checkbox (jako dnes).
- Klik na den rozbalí detail (seznam událostí toho dne) - stejná
  interakce, jakou má dnešní vestavěná karta.
- Read-only, žádné psaní/přesouvání událostí - Perioder eventy se stejně
  nedají ručně editovat, jen logovat přes existující services/entity.
- **V1 má jen měsíční view** (`dayGridMonth` ekvivalent) - žádný týden/den
  view. Rozšíření je možné později, ale není součástí v1.
- **Víc-denní pruhy nesou vlastní popisek** (např. "Perioda", "Plodné dny")
  přímo v pruhu, ne jen barvou přes legendu - textem, useknutým elipsou,
  pokud se úsek nevejde (rozhodnuto v konverzaci 2026-08-13). Barva pruhu
  je z dané kategorie, text tmavým odstínem stejné barevné řady (kontrast,
  stejná konvence jako zbytek Perioder UI).

### Konfigurační editor karty - dvouúrovňové řízení viditelnosti (rozhodnuto 2026-08-13)

Na rozdíl od původního plánu ("žádný editor karty v GUI, jen YAML") karta
**musí mít vizuální editor** (`getConfigElement()`, standardní HA custom-card
vzor) - ne proto, že by to bylo hezčí, ale kvůli oddělení dvou různých
oprávnění, která se dnes v projektu jasně rozlišují (viz sekce 2.5 - admin
rozhoduje, kdo co vidí, ne koncový uživatel karty):

1. **Editor karty (admin, konfigurační čas)** - checkboxy "které kategorie
   tahle konkrétní karta na tomhle konkrétním dashboardu vůbec smí
   nabízet" (`period`/`fertile`/`pms`/`pause`, plus **tabletka jako
   rovnocenná pátá volba** - ne vždy zapnutá napevno, rozhodnuto v
   konverzaci 2026-08-13: ne každý divák dashboardu chce vidět, jestli byla
   tabletka vzata). Totéž, co dnes admin řeší ručně přes `entities:` seznam
   v YAML (a co odlišuje `dashboard_alina.yaml` bez PMS od
   `dashboard_alina_admin.yaml` s PMS) - editor to jen dělá jako checkboxy
   místo ručního psaní entity ID.
2. **Legenda karty (kdokoli s přístupem k dashboardu, běhový čas)** -
   checkboxy pro dočasné show/hide při prohlížení, ale **jen mezi
   kategoriemi, které admin v kroku 1 povolil**. Kategorie, kterou admin
   nepovolil, se v legendě vůbec neobjeví - není to jen defaultně
   odškrtnuté, je to skutečně nedostupné, stejný princip jako u
   `binary_sensor.pms_active` a `pms_calendar` dnes (viz sekce 2.2).

Prakticky: `getConfigElement()` uloží admin výběr do `entities:` pole
karty (přesně to, co karta dnes stejně čte) - není potřeba žádný nový
datový model, jen GUI nad existujícím.

**Barvy jsou doporučení, ne napevno dané (rozhodnuto 2026-08-13):** editor
u každé povolené kategorie nabídne barevný picker předvyplněný naší
výchozí paletou (`period`=červená, `fertile`=modrá, `pms`=oranžová,
`pause`=fialová) plus tlačítko "vrátit doporučenou barvu". Admin může
kteroukoli přebít, `entities:` pak nese `color:` jen tam, kde se admin od
doporučení odchýlil (výchozí paleta zůstává fallback, stejný princip jako
dnešní `translation_key`-based default z dřívějšího návrhu). Tabletka
zůstává bez vlastní barvy (je to ikona, ne pruh) - jen on/off v editoru.

### Vizuální inspirace z jiných HACS kalendářových karet

Ověřeno 2026-08-13 proti `calendar-card-pro` (nejrozšířenější alternativa,
viz README) a obecným trendům "hezkých" HA dashboardů (mushroom/bubble
card styl, co Michael používá i jinde). Konkrétní prvky, které stojí za
převzetí do vlastní karty:

- **Odlišení víkendu** (`weekend_day_color` u calendar-card-pro) - lehčí
  odstín pro sobotu/neděli v hlavičce i čísle dne, ne nutně funkčně
  důležité, ale pomáhá rychlé orientaci v mřížce.
- **Kruhový "dnes" odznak** kolem čísla dne (ne velký obdélníkový
  highlight přes celou buňku) - čistší, méně rušivé.
- **Pastelově tónované pruhy** (tint barvy na pozadí + plná barva jako
  levý accent border + ikona) místo plných sytých pruhů - měkčí, blíž
  stylu, který Michael používá jinde (bubble card), a zároveň řeší kontrast
  textu při libovolné admin-zvolené barvě bez nutnosti počítat
  luminanci/kontrast ručně.
- **Legenda jako zaoblené "chips"** s tónovaným pozadím místo prostého
  textu + checkboxu - konzistentní s pruhy, čitelnější skupina rychle
  přepínatelných filtrů.
- **Týdenní číslo jako "pill" odznak** (`week_number_*` u
  calendar-card-pro) - zvažováno, ale vynecháno z v1 (nepřidává hodnotu
  pro tenhle konkrétní účel, jen vizuální šum navíc).

Zdroj: [alexpfau/calendar-card-pro README](https://github.com/alexpfau/calendar-card-pro/blob/main/README.md)
(sekce Visual Styling & Colors, Weekend Day Styling, Today's Date Styling).

## Technická implementace - registrace jako frontend resource

Ověřeno (2026-08-12) proti aktuálnímu (post-2024.7) HA API, ne proti
zastaralému `hass.http.register_static_path`:

1. `manifest.json` musí deklarovat `"dependencies": ["frontend", "http"]`
   (dnes Perioder nemá ani jednu - bez nich registrace tiše selže).
2. Statická cesta se registruje přes
   `await hass.http.async_register_static_paths([StaticPathConfig(url_base, path, False)])`
   (asynchronní varianta - synchronní `register_static_path` je zastaralá).
3. Samotný Lovelace resource záznam (`lovelace.resources.async_create_item(...)`)
   jde zaregistrovat **jen v storage-mode Lovelace** (výchozí režim, jaký
   Michael používá - "Přidat ovládací panel > Nový panel od začátku" je
   storage mode i když se jeden konkrétní view pak edituje přes "Upravit v
   YAML"). V čistém YAML-mode Lovelace by uživatel resource musel přidat
   ručně jednou do `ui-lovelace.yaml` - netýká se ale dnešního Perioder
   setupu.
4. **Registrace musí proběhnout v `async_setup()`, ne `async_setup_entry()`**
   - Perioder dnes `async_setup()` vůbec nemá (jen `async_setup_entry`
   per config entry) - potřeba přidat, ať se JS zaregistruje jednou za
   integraci, ne znovu za každého vlastníka cyklu.
5. Verze resource URL (`?v={manifest_version}`) se bumpuje spolu s
   `manifest.json` verzí (stejný release proces jako dnes - sekce 8) - řeší
   běžné prohlížečové/companion-app cachování staré verze JS souboru po
   aktualizaci.
6. **Souborová struktura:**
   ```
   custom_components/perioder/
     frontend/
       __init__.py          # JSModuleRegistration (viz krok 1-5)
       perioder-calendar-card.js
   ```
7. **Bez build kroku** - žádný webpack/Node/TypeScript, čistý JS modul
   (LitElement přes CDN import nebo vanilla Web Component - upřesnit při
   implementaci). Konzistentní s tím, že zbytek repozitáře je jen Python +
   YAML, žádná JS toolchain k údržbě.

Zdroje ověření: [KipK - Developer guide: Lovelace custom card embedded in
integration](https://gist.github.com/KipK/3cf706ac89573432803aaa2f5ca40492/)
(aktualizováno 2026-02-10, popisuje přesně tenhle vzor včetně
`StaticPathConfig`/`async_register_static_paths`).

## Data flow

Karta čte data přes stejné WebSocket API, jaké používá vestavěná HA karta -
`hass.callWS({type: "calendar/event/list", entity_id, start, end})` - nad
běžnými `calendar.*` entitami. **Žádná nová backendová logika v
`calendar.py` není pro v1 potřeba** - je to čistě frontendová karta nad tím,
co integrace už dnes poskytuje.

## Důsledky

- **Zjednoduší se:** žádná závislost na cizí HACS kartě a její údržbě;
  jedna verze karty, verzovaná a vydávaná spolu s integrací; barvy a
  viditelnost tabletky jde vynutit napevno, ne obchvatem.
- **Přibude práce:** JS/frontend je nová oblast údržby vedle Pythonu - repo
  dnes nemá žádné JS test tooling (`tests/` je čistě pytest, viz
  `tests/conftest.py`), takže změny v kartě se budou muset ověřovat ručně
  na živé instanci, stejné omezení, jaké má dnes i notifikační engine.
- **K revizi při implementaci:** `hacs.json`/`hassfest` validace s novou
  `frontend`/`http` závislostí a se statickým JS souborem v repozitáři -
  potvrdit, že HACS kategorie zůstává "Integration" a nevyžaduje zvláštní
  zacházení jen kvůli přibalenému JS.

## Akční kroky

1. [x] Odsouhlasit/upravit návrh výše (barvy, `pill_entity` chování,
   rozsah v1) - odsouhlaseno 2026-08-13 po několika kolech úprav (editor s
   admin-řízenou dostupností, volitelné barvy, popisky v pruzích).
2. [x] `manifest.json`: `dependencies: ["frontend", "http"]`
3. [x] `custom_components/perioder/frontend/__init__.py` -
   `JSModuleRegistration` (statická cesta + Lovelace resource, viz výše)
4. [x] `custom_components/perioder/frontend/perioder-calendar-card.js` -
   samotná karta (měsíční grid s navigací, popsané barevné pruhy,
   pill-badge, klik-detail) + `PerioderCalendarCardEditor`
   (`getConfigElement()`) - editor generický nad libovolnou `calendar.*`
   entitou (ne natvrdo vázaný na Perioder), takže funguje i kdyby admin
   chtěl přimíchat jiný kalendář.
5. [x] `async_setup()` v `__init__.py` - registruje frontend jednou za HA
   instanci, na `EVENT_HOMEASSISTANT_STARTED` (nebo hned, pokud HA už běží)
6. [ ] `hassfest`/HACS validace přes GitHub Actions - **nelze ověřit v
   tomhle prostředí** (žádná běžící HA instance ani `hassfest` nástroj
   dostupný zde) - ověří se až v CI po pushnutí/na živé instanci.
7. [x] Přepsáno `dashboard_alina.yaml`/`dashboard_alina_admin.yaml` +
   `dashboard_test.yaml`/`dashboard_test_admin.yaml` na novou kartu -
   `cycle_calendar`/`shared_calendar` zůstaly na vestavěné kartě (viz
   "Důsledky" - jsou to jednotlivé entity, nová karta jim nic nepřidává).
8. [x] `CHANGELOG.md` (v0.9.30), `manifest.json` verze, tenhle dokument
   (Status -> Accepted) odškrtnuto.

**Neověřeno živě (nutná ruční kontrola na skutečné HA instanci, viz
"Důsledky" výše):** vzhled karty v prohlížeči/Companion app, skutečná
registrace Lovelace resource po restartu, chování editoru v Lovelace UI.
JS prošel jen `node --check` (syntaxe) a samostatnými assercemi na
datumovou matematiku (týdny/měsíční mřížka, exclusive-end převod) - žádná
skutečná DOM/HA prostředí tady k dispozici.
