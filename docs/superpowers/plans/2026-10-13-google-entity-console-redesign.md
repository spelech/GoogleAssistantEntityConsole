# Google Assistant Entity Console Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 150px iframe viewport cutoff bug and modernize the Google Assistant Entity Console into a full-height, responsive UI with sticky search/filter toolbar and sticky group headers.

**Architecture:** Configure `<google-assistant-entity-console-panel>` with host block/100% styles in `panel.js`; restructure `index.html` and `style.css` into a 100vh flexbox container with fixed top bar, sticky controls, and internally scrollable table; enhance `app.js` with sticky headers, live counters, and inline alias chips.

**Tech Stack:** JavaScript (ES6+), HTML5, CSS3 (CSS Variables, Flexbox, Sticky Positioning, FontAwesome 6), Home Assistant Custom Component Panel.

## Global Constraints

- Preserve all existing API endpoints and backend compatibility in `views.py`.
- Preserve the `postMessage` token refresh mechanism (`REQUEST_HA_TOKEN` / `HA_TOKEN_UPDATE`).
- Do not introduce breaking changes to existing localStorage/sessionStorage keys (`ha_token`, filter selections).
- Support both Home Assistant Dark and Light themes through native HA CSS variables.
- Strictly prevent double scrollbars: outer container is `overflow: hidden;`, table container is `overflow-y: auto;`.

---

### Task 1: Fix Viewport Container & Panel Mounting in `panel.js`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/panel.js:20-41`

**Interfaces:**
- Consumes: Home Assistant custom panel lifecycle (`connectedCallback`, `set hass`).
- Produces: Fully expanded, full-height custom element and iframe without falling back to 150px.

- [ ] **Step 1: Inspect current `panel.js` code and identify missing styles**

Verify current contents in `custom_components/google_assistant_entity_console/static/panel.js`. Note that `connectedCallback` and `set hass` do not apply styles to `this`.

- [ ] **Step 2: Add host element full-height styling and iframe layout styling**

In `panel.js`, update `connectedCallback`:
```javascript
connectedCallback() {
  this.style.display = 'block';
  this.style.position = 'absolute';
  this.style.top = '0';
  this.style.left = '0';
  this.style.width = '100%';
  this.style.height = '100%';
  this.style.overflow = 'hidden';
  this.style.boxSizing = 'border-box';
  window.addEventListener('message', this._messageListener);
}
```
And in `set hass(hass)`:
```javascript
if (!this._iframe) {
  this._iframe = document.createElement('iframe');
  this._iframe.style.width = '100%';
  this._iframe.style.height = '100%';
  this._iframe.style.border = '0';
  this._iframe.style.display = 'block';
  this._iframe.style.overflow = 'hidden';
  this.appendChild(this._iframe);
}
```

- [ ] **Step 3: Verify syntax in node/browser**

Run: `node -c custom_components/google_assistant_entity_console/static/panel.js`
Expected: Exits with code 0 without syntax errors.

- [ ] **Step 4: Commit**

```bash
git add custom_components/google_assistant_entity_console/static/panel.js
git commit -m "fix(console): prevent 150px height collapse in panel.js"
```

---

### Task 2: Modernize HTML Shell & Sticky Toolbar Markup in `index.html`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/index.html:20-155`

**Interfaces:**
- Consumes: CSS classes and DOM IDs used by `app.js`.
- Produces: Semantic layout containing fixed header, compact stats ribbon, pinned filter toolbar, and scrollable table container.

- [ ] **Step 1: Refactor header and action buttons**

Update `<header>` in `index.html`:
- Retain logo and title.
- Add pending changes badge element (`<span id="pendingChangesBadge" class="badge-pending" style="display: none;">0 Pending</span>`).
- Organize action buttons: `AI Settings`, `Manage Blocklist`, `Sync & Rebuild`.

- [ ] **Step 2: Restructure KPI stats ribbon**

Streamline `.stats-container` to be a compact horizontal strip:
- Total Entities (`#totalEntities`)
- Exposed to Google (`#exposedEntities`)
- Pending Sync (`#pendingEntitiesCount`)
- Active YAML Config (`#configFile`)

- [ ] **Step 3: Update sticky filter toolbar structure**

Refactor `.controls-container`:
- Search box with input `#searchInput`, clear button `#clearSearchBtn`, and match counter `#filterMatchCount`.
- Filter row containing `#roomFilter`, `#groupingType`, `#exposedOnlyCheckbox`, and `#toggleAdvancedFiltersBtn`.
- Advanced filters drawer `#advancedFiltersDrawer` with `#hideGroupedLightsCheckbox`, `#hideUnavailableCheckbox`, and `#domainChipsContainer`.

- [ ] **Step 4: Update table container markup**

Ensure `#entityTable` is wrapped in `<main class="table-container" id="tableContainer">` with sticky table header `<thead>`:
- Entity (40%)
- Nicknames / Aliases (35%)
- Exposed Status (15%)
- Actions (10%)

- [ ] **Step 5: Verify HTML validity**

Check closing tags and IDs match those expected by `app.js`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/google_assistant_entity_console/static/index.html
git commit -m "feat(console): modernize HTML shell structure and sticky toolbar"
```

---

### Task 3: Overhaul CSS for 100vh Flex Shell & Sticky Elements in `style.css`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/style.css`

**Interfaces:**
- Consumes: CSS variables from Home Assistant theme (`--primary-background-color`, `--card-background-color`, etc.).
- Produces: Zero-scroll body, sticky toolbar, sticky table headers, sticky group headers, and Material 3 cards.

- [ ] **Step 1: Set up root and viewport shell styles**

In `style.css`:
```css
html, body {
  height: 100%;
  max-height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background-color: var(--primary-background-color, #111318);
  font-family: var(--font-main);
  color: var(--primary-text-color, #e2e2e9);
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 1rem 1.5rem 0.5rem 1.5rem;
  box-sizing: border-box;
  gap: 0.75rem;
  overflow: hidden;
}
```

- [ ] **Step 2: Add styles for header, compact stats ribbon, and sticky toolbar**

Style:
- `header`: compact padding (`0.75rem 1.25rem`), border radius, flex-wrap responsive.
- `.stats-container`: compact flex row, high-density cards (`padding: 0.5rem 1rem`).
- `.controls-container`: pinned with `position: relative`, `background: var(--surface)`, `border-radius: 12px`, `padding: 0.75rem 1rem`.

- [ ] **Step 3: Add styles for scrollable table container and sticky headers**

Style:
```css
.table-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  position: relative;
}

#entityTable {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

#entityTable thead th {
  position: sticky;
  top: 0;
  z-index: 5;
  background-color: var(--surface-variant);
  border-bottom: 2px solid var(--border);
  padding: 0.75rem 1rem;
}

.domain-header-row td,
.room-header-row td {
  position: sticky;
  top: 41px;
  z-index: 4;
  background-color: var(--surface-variant);
  border-bottom: 1px solid var(--border);
}
```

- [ ] **Step 4: Style modern alias chips, toggles, badges, and modals**

Style:
- `.alias-chip` with hover delete button `✕`.
- `.btn-add-alias` inline button.
- Status badges: `.badge-exposed`, `.badge-unexposed`, `.badge-pending-add`, `.badge-pending-remove`.
- Modal backdrop blur: `backdrop-filter: blur(6px); background: rgba(0, 0, 0, 0.6);`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/static/style.css
git commit -m "feat(console): overhaul CSS for 100vh flex shell and sticky headers"
```

---

### Task 4: Enhance Interactive Controls & Rendering in `app.js`

**Files:**
- Modify: `custom_components/google_assistant_entity_console/static/app.js`

**Interfaces:**
- Consumes: Entity data from `/google_assistant_entity_console/entities` and state tracking.
- Produces: Dynamic match counts, sticky group rendering, inline alias add/delete, and pending badges.

- [ ] **Step 1: Add live match counter and search clear handler**

In `app.js`:
- In `applyFilters()`, calculate filtered entity count vs total entities and update `#filterMatchCount` (e.g. `Showing 42 of 180 entities`).
- Connect `#clearSearchBtn` click event to clear `#searchInput` and re-apply filters.

- [ ] **Step 2: Update table and group row rendering**

In `renderTable()`:
- Update `.domain-header-cell` and `.room-header-cell` markup to include entity count pills and clean collapsible chevron styling.
- When rendering entity rows in `renderEntityRow(e)`:
  - Add inline `+ Add` alias button that turns into an input on click.
  - Add quick copy button for `entity_id`.
  - Display pending status badges (`Pending Add` or `Pending Remove`) and update the pending counter in header.

- [ ] **Step 3: Update pending state tracker and Rebuild button badge**

Track total pending additions and removals:
- Update `#pendingChangesBadge` visibility and text.
- If pending count > 0, highlight `#rebuildBtn` to indicate unsaved YAML changes.

- [ ] **Step 4: Verify JavaScript syntax**

Run: `node -c custom_components/google_assistant_entity_console/static/app.js`
Expected: Exits with code 0 without syntax errors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/google_assistant_entity_console/static/app.js
git commit -m "feat(console): enhance interactive table rendering and pending state"
```

---

### Task 5: Cache Busting Version Bump & End-to-End Verification

**Files:**
- Modify: `custom_components/google_assistant_entity_console/manifest.json`
- Modify: `custom_components/google_assistant_entity_console/__init__.py`

**Interfaces:**
- Consumes: HA component registration.
- Produces: Incremented cache-busting version `1.9.0` so browsers load updated assets without stale cache.

- [ ] **Step 1: Bump version in manifest.json**

Change `"version": "1.8.0"` to `"version": "1.9.0"`.

- [ ] **Step 2: Restart / reload custom component or HA container**

Run docker command or reload integration to ensure Home Assistant serves the new files.

- [ ] **Step 3: End-to-end verification via Chrome DevTools or curl**

Verify:
- Panel HTML and assets return HTTP 200 with new version query strings.
- DOM renders full-height without 150px clipping.
- Filter toolbar and sticky headers remain pinned during scroll.

- [ ] **Step 4: Commit**

```bash
git add custom_components/google_assistant_entity_console/manifest.json custom_components/google_assistant_entity_console/__init__.py
git commit -m "chore(console): bump version to 1.9.0 for asset cache busting"
```
