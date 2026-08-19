/**
 * perioder-calendar-card.js
 *
 * Vanilla Web Component (no Lit, no build step - see CALENDAR-CARD-ADR.md
 * "Zvažované varianty", option A vs B) month-grid calendar for Perioder.
 * Reads events from any `calendar.*` entity via the same REST endpoint the
 * built-in HA calendar card/dialog uses (`GET /api/calendars/{entity_id}
 * ?start=..&end=..`, called via `hass.callApi('GET', ...)` - see
 * home-assistant/frontend's `src/data/calendar.ts`, `fetchCalendarEvents`),
 * so it works with Perioder's own calendar entities without any backend
 * changes.
 *
 * v0.9.32 fix (2026-08-19): the first live test rendered the header/legend/
 * grid fine but showed zero events on any day. Root cause - this card used
 * to call `hass.callWS({type: 'calendar/event/list', ...})`, a websocket
 * command that **does not exist** in HA core (confirmed against
 * home-assistant/core's `calendar/__init__.py` on the `dev` branch - the
 * only registered `calendar/event/*` WS commands are `create`/`update`/
 * `delete`/`subscribe`, none named `list`). Every call therefore threw,
 * was swallowed by the per-entity `try/catch` here, and silently resolved
 * to an empty event list for every entity - card looked "connected" but
 * never had anything to draw. Fixed by switching to the REST endpoint
 * above, which is what HA's own calendar card/dialog actually use.
 *
 * Two problems this exists to solve (see calendar.py's own docstring +
 * CALENDAR-CARD-ADR.md for the full history):
 *   1. The built-in card can't pin a fixed color per calendar entity -
 *      colors are auto-assigned by list order. This card takes an explicit
 *      `color` per entity in its config (admin-editable, defaults supplied,
 *      never forced).
 *   2. The built-in card (FullCalendar) sorts a day's events
 *      longest-duration-first, so a single-day "pill taken" event sharing a
 *      day with a multi-day period/fertile block always lost and collapsed
 *      into a "+n more" popover. This card renders one optional
 *      `pill_entity` as a small badge icon on the day cell, completely
 *      outside the multi-day event lanes - it can never be hidden by
 *      anything else on that day.
 *
 * Config shape:
 *   type: custom:perioder-calendar-card
 *   title: Kalendář cyklu
 *   entities:
 *     - entity: calendar.alina_period_calendar
 *       color: "#E24B4A"      # optional, admin can override via the editor
 *       icon: mdi:water        # optional, guessed from entity_id otherwise
 *   pill_entity: calendar.alina_pill_calendar   # optional
 *
 * All-day event date semantics follow the same convention calendar.py
 * already uses throughout (end date is EXCLUSIVE - "start <= day < end"),
 * which is also what Home Assistant's `/api/calendars/{entity_id}` REST
 * endpoint returns for all-day CalendarEvents (`{"date": "YYYY-MM-DD"}`
 * per event's `start`/`end` - see `_api_event_dict_factory` in
 * home-assistant/core's `calendar/__init__.py`).
 */

const DEFAULT_COLORS = ['#E24B4A', '#378ADD', '#BA7517', '#7F77DD', '#1D9E75', '#D4537E'];

const ICON_GUESS = [
  [/period_calendar$/, 'mdi:water'],
  [/fertile_calendar$/, 'mdi:flower'],
  [/pms_calendar$/, 'mdi:weather-cloudy'],
  [/pause_calendar$/, 'mdi:moon-waning-crescent'],
  [/pill_calendar$/, 'mdi:pill'],
  [/cycle_calendar$/, 'mdi:calendar-heart'],
  [/shared_calendar$/, 'mdi:calendar-account'],
];

function guessIcon(entityId) {
  for (const [pattern, icon] of ICON_GUESS) {
    if (pattern.test(entityId)) return icon;
  }
  return 'mdi:calendar-blank';
}

function fmtDate(date) {
  return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
}

function addDays(dateStr, delta) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + delta);
  return fmtDate(d);
}

function eventDateStr(part) {
  // part is HA's {date} or {dateTime} shape for one end of an event.
  if (!part) return '';
  return part.date || (part.dateTime || '').slice(0, 10);
}

function buildWeeks(year, monthIndex) {
  const first = new Date(year, monthIndex, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(year, monthIndex, 1 - startOffset);
  const weeks = [];
  let cursor = new Date(gridStart);
  for (let w = 0; w < 6; w++) {
    const week = [];
    let inMonth = false;
    for (let d = 0; d < 7; d++) {
      const day = new Date(cursor);
      if (day.getMonth() === monthIndex) inMonth = true;
      week.push(day);
      cursor.setDate(cursor.getDate() + 1);
    }
    if (inMonth) weeks.push(week);
  }
  return weeks;
}

function hexTint(hex) {
  return hex + '26';
}

const MONTH_NAMES = ['Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen', 'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec'];
const WEEKDAY_NAMES = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'];

class PerioderCalendarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    const now = new Date();
    this._viewYear = now.getFullYear();
    this._viewMonth = now.getMonth();
    this._events = {};
    this._expandedDay = null;
    this._fetchToken = 0;
    // v0.9.33: runtime-only legend toggle state (which entities are
    // hidden right now) - like the built-in calendar card's per-entity
    // checkboxes, this is a view preference, not something written back
    // to the dashboard config, so it resets on page reload. Keyed by
    // entity_id (works for both category entities and pill_entity).
    this._hiddenEntities = new Set();
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error('perioder-calendar-card: nastav aspoň jednu entitu v "entities"');
    }
    this._config = config;
    this._render();
    this._fetchEvents();
  }

  set hass(hass) {
    const hadHass = !!this._hass;
    this._hass = hass;
    if (!this._config) return;
    if (!hadHass) this._fetchEvents();
    else this._render();
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig(hass) {
    const calendars = Object.keys((hass && hass.states) || {}).filter((e) => e.startsWith('calendar.'));
    return {
      type: 'custom:perioder-calendar-card',
      title: 'Kalendář cyklu',
      entities: calendars.slice(0, 4).map((entity, i) => ({ entity, color: DEFAULT_COLORS[i % DEFAULT_COLORS.length] })),
    };
  }

  static getConfigElement() {
    return document.createElement('perioder-calendar-card-editor');
  }

  async _fetchEvents() {
    if (!this._hass || !this._config) return;
    const token = ++this._fetchToken;

    const monthStart = new Date(this._viewYear, this._viewMonth, 1);
    const monthEnd = new Date(this._viewYear, this._viewMonth + 1, 0);
    const gridStart = new Date(monthStart);
    gridStart.setDate(gridStart.getDate() - ((gridStart.getDay() + 6) % 7));
    const gridEnd = new Date(monthEnd);
    gridEnd.setDate(gridEnd.getDate() + (6 - ((gridEnd.getDay() + 6) % 7)));
    gridEnd.setDate(gridEnd.getDate() + 1);

    const entityIds = (this._config.entities || []).map((e) => e.entity);
    if (this._config.pill_entity) entityIds.push(this._config.pill_entity);

    const results = {};
    const qs =
      '?start=' + encodeURIComponent(gridStart.toISOString()) + '&end=' + encodeURIComponent(gridEnd.toISOString());
    await Promise.all(
      entityIds.map(async (entityId) => {
        try {
          // REST, not WS - see module docstring "v0.9.32 fix". Response is
          // a bare array of events (not wrapped in `{events: [...]}` the
          // way the old, nonexistent WS call would have been).
          const res = await this._hass.callApi('GET', 'calendars/' + encodeURIComponent(entityId) + qs);
          results[entityId] = Array.isArray(res) ? res : [];
        } catch (err) {
          results[entityId] = [];
        }
      })
    );

    if (token !== this._fetchToken) return;
    this._events = results;
    this._render();
  }

  _changeMonth(delta) {
    this._viewMonth += delta;
    if (this._viewMonth < 0) {
      this._viewMonth = 11;
      this._viewYear -= 1;
    } else if (this._viewMonth > 11) {
      this._viewMonth = 0;
      this._viewYear += 1;
    }
    this._expandedDay = null;
    this._fetchEvents();
  }

  _entityName(entityId) {
    const state = this._hass && this._hass.states[entityId];
    return (state && state.attributes.friendly_name) || entityId;
  }

  _dayHasEvent(entityId, dateStr) {
    const events = this._events[entityId] || [];
    return events.some((ev) => {
      const start = eventDateStr(ev.start);
      const end = eventDateStr(ev.end);
      return start <= dateStr && dateStr < end;
    });
  }

  _segmentsForWeek(entityId, week) {
    const events = this._events[entityId] || [];
    const weekStartStr = fmtDate(week[0]);
    const weekEndStr = fmtDate(week[6]);
    const segments = [];

    events.forEach((ev) => {
      const startStr = eventDateStr(ev.start);
      const endExclusiveStr = eventDateStr(ev.end);
      if (!startStr || !endExclusiveStr) return;
      const endInclusiveStr = addDays(endExclusiveStr, -1);
      if (endInclusiveStr < weekStartStr || startStr > weekEndStr) return;

      let startCol = null;
      let endCol = null;
      week.forEach((d, i) => {
        const dStr = fmtDate(d);
        if (dStr >= startStr && dStr <= endInclusiveStr) {
          if (startCol === null) startCol = i;
          endCol = i;
        }
      });
      if (startCol === null) return;

      segments.push({
        startCol,
        endCol,
        isStart: fmtDate(week[startCol]) === startStr,
        isEnd: fmtDate(week[endCol]) === endInclusiveStr,
        summary: ev.summary,
      });
    });

    return segments;
  }

  _renderDetail(dateStr) {
    const rows = [];
    (this._config.entities || [])
      .filter((entCfg) => !this._hiddenEntities.has(entCfg.entity))
      .forEach((entCfg) => {
        const events = this._events[entCfg.entity] || [];
        events.forEach((ev) => {
          const start = eventDateStr(ev.start);
          const end = eventDateStr(ev.end);
          if (start <= dateStr && dateStr < end) {
            rows.push({
              color: entCfg.color || DEFAULT_COLORS[0],
              icon: entCfg.icon || guessIcon(entCfg.entity),
              text: ev.summary || this._entityName(entCfg.entity),
            });
          }
        });
      });
    if (this._config.pill_entity && !this._hiddenEntities.has(this._config.pill_entity)) {
      const events = this._events[this._config.pill_entity] || [];
      events.forEach((ev) => {
        const start = eventDateStr(ev.start);
        const end = eventDateStr(ev.end);
        if (start <= dateStr && dateStr < end) {
          rows.push({ color: 'var(--primary-color)', icon: 'mdi:pill', text: ev.summary || 'Tabletka' });
        }
      });
    }
    const dateLabel = (() => {
      const d = new Date(dateStr + 'T00:00:00');
      return d.getDate() + '. ' + MONTH_NAMES[d.getMonth()].toLowerCase() + ' ' + d.getFullYear();
    })();
    const rowsHtml =
      rows.length === 0
        ? '<span class="empty">Žádné události</span>'
        : rows
            .map(
              (r) =>
                '<div class="detail-row"><ha-icon icon="' +
                r.icon +
                '" style="color:' +
                r.color +
                ';"></ha-icon><span>' +
                r.text +
                '</span></div>'
            )
            .join('');
    return '<div class="detail"><div class="detail-date">' + dateLabel + '</div>' + rowsHtml + '</div>';
  }

  _toggleHidden(entityId) {
    if (this._hiddenEntities.has(entityId)) this._hiddenEntities.delete(entityId);
    else this._hiddenEntities.add(entityId);
    this._render();
  }

  _render() {
    if (!this._config) return;
    const cfg = this._config;
    const weeks = buildWeeks(this._viewYear, this._viewMonth);
    const todayStr = fmtDate(new Date());
    const catEntities = cfg.entities || [];
    const pillEntity = cfg.pill_entity;
    const hidden = this._hiddenEntities;
    // v0.9.33: only entities the legend hasn't toggled off actually get a
    // lane row - keeps bars packed with no gap left behind by a hidden
    // category, same "hide via legend" UX as the built-in calendar card's
    // per-entity checkboxes (default colors/lane-count still key off the
    // *full* list below so toggling one entity off doesn't reflow colors).
    const visibleCat = catEntities.filter((e) => !hidden.has(e.entity));

    // v0.9.33 grid rewrite: day numbers and event bars used to be two
    // separate CSS grids stacked with a margin between them, which read as
    // two disconnected pieces (day numbers "floating" above bars that
    // visually belonged to no particular row). Both now live in ONE grid
    // per week: row 1 = day cells (which span every row via `grid-row:1/-1`
    // in CSS so their border/background reaches down behind that day's
    // bars, like a real calendar cell), rows 2+ = event bars. Clicking
    // anywhere in a day's column (not just the number) expands that day.
    let gridHtml = '';
    weeks.forEach((week) => {
      let dayCellsHtml = '';
      week.forEach((date, i) => {
        const dateStr = fmtDate(date);
        const inMonth = date.getMonth() === this._viewMonth;
        const isToday = dateStr === todayStr;
        const isWeekend = i >= 5;
        const isSelected = this._expandedDay === dateStr;
        const hasPill = pillEntity && !hidden.has(pillEntity) && this._dayHasEvent(pillEntity, dateStr);
        dayCellsHtml +=
          '<div class="day' +
          (inMonth ? '' : ' outside') +
          (isSelected ? ' selected' : '') +
          '" style="grid-column:' +
          (i + 1) +
          ';" data-date="' +
          dateStr +
          '"><span class="daynum' +
          (isToday ? ' today' : '') +
          (isWeekend && !isToday ? ' weekend' : '') +
          '">' +
          date.getDate() +
          '</span>' +
          (hasPill ? '<ha-icon class="pill-badge" icon="mdi:pill"></ha-icon>' : '') +
          '</div>';
      });

      // v0.9.33: pack bars into as few lane rows as possible *for this
      // specific week*, instead of giving every category a permanently
      // reserved row across the whole month. Period/fertile window/pause
      // rarely overlap each other on the same days, so a fixed per-category
      // lane wasted a lot of vertical space on weeks with only one active
      // bar (2-3 empty reserved rows every week). Classic greedy interval
      // scheduling: sort segments left-to-right, drop each into the first
      // lane whose last-placed segment ends before this one starts.
      const weekSegments = [];
      visibleCat.forEach((entCfg) => {
        const fullIdx = catEntities.indexOf(entCfg);
        const color = entCfg.color || DEFAULT_COLORS[fullIdx % DEFAULT_COLORS.length];
        const icon = entCfg.icon || guessIcon(entCfg.entity);
        this._segmentsForWeek(entCfg.entity, week).forEach((seg) => {
          weekSegments.push(Object.assign({ color, icon, name: this._entityName(entCfg.entity) }, seg));
        });
      });
      weekSegments.sort((a, b) => a.startCol - b.startCol || b.endCol - b.startCol - (a.endCol - a.startCol));
      const laneEnds = [];
      weekSegments.forEach((seg) => {
        let lane = laneEnds.findIndex((endCol) => endCol < seg.startCol);
        if (lane === -1) {
          lane = laneEnds.length;
          laneEnds.push(seg.endCol);
        } else {
          laneEnds[lane] = seg.endCol;
        }
        seg.lane = lane;
      });
      const weekLaneCount = laneEnds.length;

      let lanesHtml = '';
      weekSegments.forEach((seg) => {
        let radius = '0';
        if (seg.isStart && seg.isEnd) radius = '8px';
        else if (seg.isStart) radius = '8px 0 0 8px';
        else if (seg.isEnd) radius = '0 8px 8px 0';
        lanesHtml +=
          '<div class="bar" style="grid-column:' +
          (seg.startCol + 1) +
          ' / ' +
          (seg.endCol + 2) +
          '; grid-row:' +
          (seg.lane + 2) +
          '; background:' +
          hexTint(seg.color) +
          '; border-left-color:' +
          seg.color +
          '; border-radius:' +
          radius +
          ';">' +
          (seg.isStart
            ? '<ha-icon icon="' + seg.icon + '" style="color:' + seg.color + ';"></ha-icon><span>' + seg.name + '</span>'
            : '') +
          '</div>';
      });

      gridHtml +=
        '<div class="week" style="grid-template-rows:26px repeat(' +
        Math.max(weekLaneCount, 1) +
        ',18px);">' +
        dayCellsHtml +
        lanesHtml +
        '</div>';

      if (this._expandedDay && week.some((d) => fmtDate(d) === this._expandedDay)) {
        gridHtml += this._renderDetail(this._expandedDay);
      }
    });

    const legendHtml =
      catEntities
        .map((entCfg, i) => {
          const color = entCfg.color || DEFAULT_COLORS[i % DEFAULT_COLORS.length];
          const icon = entCfg.icon || guessIcon(entCfg.entity);
          const isOff = hidden.has(entCfg.entity);
          return (
            '<button type="button" class="chip' +
            (isOff ? ' chip-off' : '') +
            '" data-toggle="' +
            entCfg.entity +
            '" style="background:' +
            hexTint(color) +
            ';" aria-pressed="' +
            (!isOff) +
            '"><ha-icon icon="' +
            icon +
            '" style="color:' +
            color +
            ';"></ha-icon>' +
            this._entityName(entCfg.entity) +
            '</button>'
          );
        })
        .join('') +
      (pillEntity
        ? '<button type="button" class="chip pill-chip' +
          (hidden.has(pillEntity) ? ' chip-off' : '') +
          '" data-toggle="' +
          pillEntity +
          '" aria-pressed="' +
          !hidden.has(pillEntity) +
          '"><ha-icon icon="mdi:pill"></ha-icon>' +
          this._entityName(pillEntity) +
          '</button>'
        : '');

    this.shadowRoot.innerHTML =
      '<style>' +
      'ha-card{padding:16px;}' +
      '.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}' +
      '.header .title{font-size:16px;font-weight:500;color:var(--primary-text-color);}' +
      '.header .nav{display:flex;align-items:center;gap:2px;font-size:13px;color:var(--primary-text-color);}' +
      '.header button{background:none;border:none;cursor:pointer;color:var(--primary-text-color);padding:4px;display:flex;border-radius:6px;}' +
      '.header button:hover{background:var(--secondary-background-color);}' +
      '.legend{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;}' +
      '.chip{display:inline-flex;align-items:center;gap:6px;font-size:13px;padding:4px 10px 4px 8px;border-radius:999px;color:var(--primary-text-color);border:none;font-family:inherit;cursor:pointer;opacity:1;transition:opacity .15s ease;}' +
      '.chip:hover{opacity:0.8;}' +
      '.chip:focus-visible{outline:2px solid var(--primary-color);outline-offset:1px;}' +
      '.chip.chip-off{opacity:0.4;}' +
      '.chip.pill-chip{background:rgba(var(--rgb-primary-color,3,169,244),0.15);}' +
      '.chip ha-icon,.bar ha-icon,.pill-badge{--mdc-icon-size:14px;}' +
      '.month-grid{border:1px solid var(--divider-color);border-radius:10px;overflow:hidden;}' +
      '.weekdays{display:grid;grid-template-columns:repeat(7,1fr);background:var(--secondary-background-color);border-bottom:1px solid var(--divider-color);}' +
      '.weekdays span{font-size:11px;text-transform:uppercase;letter-spacing:.02em;text-align:center;color:var(--secondary-text-color);padding:6px 0;}' +
      '.week{position:relative;display:grid;grid-template-columns:repeat(7,1fr);column-gap:2px;row-gap:3px;padding-top:2px;border-bottom:1px solid var(--divider-color);}' +
      '.week:last-of-type{border-bottom:none;}' +
      '.day{position:relative;grid-row:1 / -1;padding:4px;cursor:pointer;border-right:1px solid var(--divider-color);transition:background .1s ease;}' +
      '.day:hover{background:var(--secondary-background-color);}' +
      '.day.selected{background:rgba(var(--rgb-primary-color,3,169,244),0.12);box-shadow:inset 0 0 0 1px var(--primary-color);border-radius:4px;}' +
      '.day:nth-child(7n){border-right:none;}' +
      '.day.outside{opacity:0.35;}' +
      '.daynum{font-size:12px;color:var(--primary-text-color);}' +
      '.daynum.weekend{color:var(--secondary-text-color);}' +
      '.daynum.today{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:999px;background:var(--primary-color);color:var(--text-primary-color);}' +
      '.pill-badge{position:absolute;top:4px;right:4px;color:var(--primary-color);}' +
      '.bar{display:flex;align-items:center;gap:4px;height:18px;font-size:10px;font-weight:500;padding-left:5px;border-left:3px solid;overflow:hidden;white-space:nowrap;color:var(--primary-text-color);pointer-events:none;}' +
      '.bar span{overflow:hidden;text-overflow:ellipsis;}' +
      '.detail{margin:2px 2px 6px;padding:8px 10px;border-radius:8px;background:var(--secondary-background-color);font-size:13px;}' +
      '.detail-date{font-weight:500;color:var(--primary-text-color);margin-bottom:4px;}' +
      '.detail-row{display:flex;align-items:center;gap:6px;padding:2px 0;color:var(--primary-text-color);}' +
      '.detail-row ha-icon{--mdc-icon-size:16px;}' +
      '.detail .empty{color:var(--secondary-text-color);}' +
      '</style>' +
      '<ha-card>' +
      '<div class="header">' +
      '<span class="title">' +
      (cfg.title || '') +
      '</span>' +
      '<div class="nav">' +
      '<button aria-label="Předchozí měsíc" data-nav="-1"><ha-icon icon="mdi:chevron-left"></ha-icon></button>' +
      '<span>' +
      MONTH_NAMES[this._viewMonth] +
      ' ' +
      this._viewYear +
      '</span>' +
      '<button aria-label="Další měsíc" data-nav="1"><ha-icon icon="mdi:chevron-right"></ha-icon></button>' +
      '</div>' +
      '</div>' +
      '<div class="legend">' +
      legendHtml +
      '</div>' +
      '<div class="month-grid">' +
      '<div class="weekdays">' +
      WEEKDAY_NAMES.map((w) => '<span>' + w + '</span>').join('') +
      '</div>' +
      gridHtml +
      '</div>' +
      '</ha-card>';

    this.shadowRoot.querySelectorAll('button[data-nav]').forEach((btn) => {
      btn.addEventListener('click', () => this._changeMonth(parseInt(btn.dataset.nav, 10)));
    });
    this.shadowRoot.querySelectorAll('.chip[data-toggle]').forEach((btn) => {
      btn.addEventListener('click', () => this._toggleHidden(btn.dataset.toggle));
    });
    this.shadowRoot.querySelectorAll('.day').forEach((el) => {
      el.addEventListener('click', () => {
        this._expandedDay = this._expandedDay === el.dataset.date ? null : el.dataset.date;
        this._render();
      });
    });
  }
}

class PerioderCalendarCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    this._config = config || { entities: [] };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _calendarEntities() {
    if (!this._hass) return [];
    return Object.keys(this._hass.states)
      .filter((e) => e.startsWith('calendar.'))
      .sort();
  }

  _entryFor(entityId) {
    // v0.9.32 fix: `hass` can be set on the editor element before
    // `setConfig()` ever runs (HA's dashboard editor doesn't guarantee
    // ordering), which used to throw "Cannot read properties of
    // undefined (reading 'entities')" here - `this._config` itself was
    // undefined at that point, not just `.entities`. Guard both.
    return ((this._config && this._config.entities) || []).find((e) => e.entity === entityId);
  }

  _updateConfig(newConfig) {
    this._config = newConfig;
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: newConfig }, bubbles: true, composed: true }));
  }

  _toggleEntity(entityId, checked, defaultColor) {
    // v0.9.32 fix: same `this._config` may-be-undefined race as
    // `_entryFor` - guard before reading `.entities` off it.
    let entities = ((this._config && this._config.entities) || []).slice();
    if (checked) {
      if (!entities.some((e) => e.entity === entityId)) {
        entities.push({ entity: entityId, color: defaultColor });
      }
    } else {
      entities = entities.filter((e) => e.entity !== entityId);
    }
    this._updateConfig(Object.assign({}, this._config, { entities }));
  }

  _setColor(entityId, color) {
    const entities = ((this._config && this._config.entities) || []).map((e) =>
      e.entity === entityId ? Object.assign({}, e, { color }) : e
    );
    this._updateConfig(Object.assign({}, this._config, { entities }));
  }

  _setPill(entityId, checked) {
    const currentPill = this._config && this._config.pill_entity;
    const nextPill = checked ? entityId : currentPill === entityId ? undefined : currentPill;
    const next = Object.assign({}, this._config, { pill_entity: nextPill });
    if (nextPill === undefined) delete next.pill_entity;
    this._updateConfig(next);
  }

  _setTitle(title) {
    this._updateConfig(Object.assign({}, this._config, { title }));
  }

  _render() {
    if (!this._hass) return;
    const entities = this._calendarEntities();
    const cfg = this._config || {};
    const rowsHtml = entities
      .map((entityId, i) => {
        const entry = this._entryFor(entityId);
        const included = !!entry;
        const isPill = cfg.pill_entity === entityId;
        const defaultColor = DEFAULT_COLORS[i % DEFAULT_COLORS.length];
        const color = (entry && entry.color) || defaultColor;
        const name = (this._hass.states[entityId] && this._hass.states[entityId].attributes.friendly_name) || entityId;
        return (
          '<div class="row" data-entity="' +
          entityId +
          '" data-default-color="' +
          defaultColor +
          '">' +
          '<input type="checkbox" class="incl" ' +
          (included ? 'checked' : '') +
          '>' +
          '<input type="color" class="color" value="' +
          color +
          '" ' +
          (included ? '' : 'disabled') +
          '>' +
          '<button class="reset" type="button" title="Vrátit doporučenou barvu" aria-label="Vrátit doporučenou barvu">↺</button>' +
          '<span class="name">' +
          name +
          '</span>' +
          '<label class="pill-toggle"><input type="checkbox" class="pill" ' +
          (isPill ? 'checked' : '') +
          '>tabletka</label>' +
          '</div>'
        );
      })
      .join('');

    this.shadowRoot.innerHTML =
      '<style>' +
      '.field{margin-bottom:12px;}' +
      '.field label{display:block;font-size:13px;color:var(--secondary-text-color);margin-bottom:4px;}' +
      '.field input[type=text]{width:100%;box-sizing:border-box;padding:8px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);}' +
      '.hint{font-size:12px;color:var(--secondary-text-color);margin-bottom:8px;}' +
      '.row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--divider-color);}' +
      '.row .name{flex:1;font-size:13px;color:var(--primary-text-color);}' +
      '.row .color{width:24px;height:24px;padding:0;border:none;border-radius:4px;cursor:pointer;}' +
      '.row .reset{background:none;border:none;cursor:pointer;color:var(--secondary-text-color);}' +
      '.pill-toggle{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--secondary-text-color);}' +
      '</style>' +
      '<div class="field"><label>Titulek karty</label><input type="text" class="title" value="' +
      (cfg.title || '') +
      '"></div>' +
      '<div class="hint">Barvy jsou jen doporučení, klidně je přebij. "tabletka" smí být zaškrtnutá jen u jedné entity - vykreslí se jako ikonka na dni místo pruhu.</div>' +
      '<div class="rows">' +
      rowsHtml +
      '</div>';

    this.shadowRoot.querySelector('.title').addEventListener('change', (e) => this._setTitle(e.target.value));
    this.shadowRoot.querySelectorAll('.row').forEach((row) => {
      const entityId = row.dataset.entity;
      const defaultColor = row.dataset.defaultColor;
      row.querySelector('.incl').addEventListener('change', (e) => this._toggleEntity(entityId, e.target.checked, defaultColor));
      row.querySelector('.color').addEventListener('input', (e) => this._setColor(entityId, e.target.value));
      row.querySelector('.reset').addEventListener('click', () => {
        this._setColor(entityId, defaultColor);
        row.querySelector('.color').value = defaultColor;
      });
      row.querySelector('.pill').addEventListener('change', (e) => this._setPill(entityId, e.target.checked));
    });
  }
}

customElements.define('perioder-calendar-card', PerioderCalendarCard);
customElements.define('perioder-calendar-card-editor', PerioderCalendarCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'perioder-calendar-card',
  name: 'Perioder – kalendář cyklu',
  description: 'Měsíční kalendář s pevnými barvami po kategoriích a vždy viditelnou ikonkou tabletky.',
  preview: true,
});
