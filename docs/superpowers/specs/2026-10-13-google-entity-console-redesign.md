# Google Assistant Entity Console — UI Rework & Layout Fix Specification

- **Date**: 2026-10-13
- **Component**: `custom_components/google_assistant_entity_console`
- **Target URL Path**: `/google_assistant_entity_console`
- **Status**: Approved Design

---

## 1. Problem Statement & Root Cause

### 1.1 The Viewport Cut-off Bug
In Home Assistant, the custom panel registered via `async_register_built_in_panel` mounts `<google-assistant-entity-console-panel>` into `<ha-panel-custom>`.
- In `panel.js`, the custom element `GoogleAssistantEntityConsolePanel` does not specify host styling (`display: block; width: 100%; height: 100%`).
- By default, custom HTML elements are `display: inline;`.
- The child `iframe` has `height: 100%`. Under standard CSS specifications, a child percentage height inside an element with unresolved/inline height falls back to the browser intrinsic default iframe height of **150px**.
- As a consequence, the console UI renders inside a 150px window, clipping everything immediately below the top header cards.

### 1.2 UX Limitations in Current Design
- **Rigid Centered Width**: `index.html` wraps the entire app in `max-width: 1200px`, creating giant empty side gutters on widescreen displays and cramped columns on medium viewports.
- **Lost Controls on Scroll**: As users scroll down hundreds of smart home entities, the search input, room filter, and grouping controls scroll out of view, forcing constant scrolling up and down.
- **Column Density & Wrapping**: Nickname chips and status badges cause uneven row heights without clear horizontal boundaries.
- **Hardcoded Theme Fallbacks**: Dark-mode colors with hardcoded dark hex values cause poor contrast or visual seams when Home Assistant runs custom or light themes.

---

## 2. Architectural Design

```
+-----------------------------------------------------------------------------------+
| Host: <google-assistant-entity-console-panel> (display: block; width/height: 100%)|
| Child: <iframe src="index.html"> (width: 100%; height: 100%; border: 0)          |
+-----------------------------------------------------------------------------------+
| iframe contents (100vh flexbox container, overflow: hidden):                     |
|                                                                                   |
|  [Header & Action Bar]                                          (fixed height)    |
|    - Logo + Title ("Google Assistant Entity Console")                             |
|    - Pending Changes Badge                                                        |
|    - AI Settings | Manage Blocklist | Sync & Rebuild Actions                      |
|                                                                                   |
|  [Compact KPI Stats Ribbon]                                     (fixed height)    |
|    - Total Entities | Exposed | Unexposed | Active YAML config                    |
|                                                                                   |
|  [Sticky Filter & Search Toolbar]                               (sticky / pinned) |
|    - Search input (live debounce, clear button, match counter)                   |
|    - Room filter dropdown | Grouping selector | Exposed Only toggle               |
|    - Advanced Filters drawer toggle (Hide Grouped, Hide Unavailable, Domain chips)|
|                                                                                   |
|  [Scrollable Data Grid Viewport]                                (flex: 1, auto)   |
|    +---------------------------------------------------------------------------+  |
|    | Sticky Table Header: [Entity] [Nicknames/Aliases] [Exposed Status][Actions|  |
|    | Sticky Group Banner: Living Room (8 entities)                 [AI Assist] |  |
|    |   - light.ceiling_light | [Living Room Light (x)] [+ Add] | [ON] [Exposed]|  |
|    |   - switch.coffee_maker | [Coffee (x)]            [+ Add] | [OFF][Not Exp]|  |
|    | Sticky Group Banner: Kitchen (5 entities)                     [AI Assist] |  |
|    |   ...                                                                     |  |
|    +---------------------------------------------------------------------------+  |
|                                                                                   |
|  [Modals: AI Settings, AI Assist, Blocklist, Restart Confirmation]                |
+-----------------------------------------------------------------------------------+
```

---

## 3. Detailed Component Specifications

### 3.1 Host Panel Mounting (`panel.js`)
- Enforce full parent expansion in `connectedCallback`:
  ```javascript
  this.style.display = 'block';
  this.style.width = '100%';
  this.style.height = '100%';
  this.style.position = 'absolute';
  this.style.top = '0';
  this.style.left = '0';
  this.style.right = '0';
  this.style.bottom = '0';
  this.style.overflow = 'hidden';
  this.style.boxSizing = 'border-box';
  ```
- Ensure `_iframe` styles are set to `width: 100%; height: 100%; border: none; display: block; overflow: hidden;`.
- Maintain bidirectional `postMessage` token refresh handshake (`REQUEST_HA_TOKEN` / `HA_TOKEN_UPDATE`).

### 3.2 Viewport Shell & Theme Integration (`style.css` & `index.html`)
- **Container Structure**:
  - `html, body`: `height: 100%; max-height: 100vh; margin: 0; padding: 0; overflow: hidden; background: var(--primary-background-color, #111318); font-family: var(--paper-font-common-font-family, Roboto, sans-serif); color: var(--primary-text-color, #e2e2e9);`.
  - `.app-container`: `display: flex; flex-direction: column; height: 100vh; width: 100%; max-width: 100%; margin: 0; padding: 1.25rem 2rem 0.5rem 2rem; box-sizing: border-box; gap: 0.75rem;`.
- **Theme Variables**:
  - Surface backgrounds: `var(--card-background-color, #1a1c22)` and `var(--secondary-background-color, #22252c)`.
  - Borders and dividers: `var(--divider-color, rgba(255, 255, 255, 0.12))`.
  - Accents: `var(--primary-color, #a8c7fa)`, `var(--success-color, #3ddc84)`, `var(--error-color, #ffb4ab)`.

### 3.3 Header & Sticky Filter Toolbar
- **Header**:
  - Sleek top bar with app icon, title, active YAML config file tag, and action buttons (`AI Settings`, `Blocklist`, `Sync & Rebuild`).
  - Rebuild button dynamically pulses or shows a badge when there are unsaved pending exposure additions or removals.
- **KPI Stats Ribbon**:
  - Compact cards with clean typography and subtle icons: Total Entities, Exposed to Google, Pending Changes, Active YAML file.
- **Sticky Controls Toolbar**:
  - Pinned directly above the table container.
  - Search input with clear button and live counter (`Showing X of Y entities`).
  - Room dropdown selector, Grouping mode (`Floor & Room`, `Domain`, `Flat List`).
  - Toggle switches: `Exposed Only`, `Pending Changes Only`.
  - Advanced filters button with collapsible drawer for domain chips (`light`, `switch`, `climate`, `sensor`, etc.) and exclusion toggles (`Hide Grouped Lights`, `Hide Unavailable`).

### 3.4 Entity Data Grid & Interactions (`app.js`)
- **Sticky Column Headers**: Table header remains visible at `top: 0` inside the scroll container.
- **Sticky Group Rows**:
  - Domain or Room headers stick at `top: 38px` with clear contrast and high z-index while scrolling within that group.
  - Group header contains fold/unfold chevron, group title, entity count badge, and a group-level `AI Assist` launcher.
- **Interactive Row Columns**:
  1. **Entity**: Domain icon badge, friendly name (bold), entity_id chip with copy-to-clipboard, optional `unavailable` warning indicator.
  2. **Nicknames & Aliases**:
     - Chips with delete button (`✕`).
     - Inline `+ Add` button that turns into an input field on click (adds on Enter or blur).
     - Per-entity AI sparkle button for room-aware alias generation.
  3. **Exposed Status**:
     - Modern toggle switch.
     - State pill: `Exposed`, `Not Exposed`, `Pending Add` (amber), `Pending Remove` (orange).
  4. **Actions**:
     - Quick shortcut to add entity pattern to regex blocklist.

### 3.5 Modals & Dialogs
- Backdrop blur (`backdrop-filter: blur(6px); background: rgba(0, 0, 0, 0.6)`).
- Centered cards with header, scrollable body (`max-height: 70vh; overflow-y: auto`), and pinned action bar.
- Supported Modals:
  - **AI Settings Modal**: OpenAI / HA agent selector, endpoint and key inputs, model fetcher, prompt template editors, prompt variable legend.
  - **AI Assist Modal**: Exposure analysis with intent input, live generation spinner, review list with checkboxes, and batch apply.
  - **Blocklist Modal**: Regex pattern list with delete buttons and add input.
  - **Restart Confirmation Modal**: Missing include instruction card with one-click copy, confirmation buttons.

---

## 4. Deliverables & Files to Modify

1. `custom_components/google_assistant_entity_console/static/panel.js`
   - Fix host element positioning, width, height, and display properties.
2. `custom_components/google_assistant_entity_console/static/index.html`
   - Modernize shell structure, header actions, stats ribbon, sticky toolbar, and table wrapper.
3. `custom_components/google_assistant_entity_console/static/style.css`
   - Complete layout overhaul for 100vh viewport shell, sticky toolbar, sticky table headers/groups, MD3 chips and inputs, modal backdrops.
4. `custom_components/google_assistant_entity_console/static/app.js`
   - Enhance table rendering for sticky groups, live filter counters, inline alias adding, and pending badges.
5. Cache busting version bump in `custom_components/google_assistant_entity_console/manifest.json` and `views.py`.

---

## 5. Verification Plan
- Verify `<google-assistant-entity-console-panel>` expands to full height without collapsing to 150px.
- Verify scrolling: ensure the filter toolbar stays pinned while scrolling through hundreds of entities.
- Verify sticky group headers stick properly underneath the table header during scroll.
- Verify search, filtering, alias adding/removing, exposure toggling, and rebuild modal workflows operate smoothly.
- Test in both dark and light modes for contrast and legibility.
