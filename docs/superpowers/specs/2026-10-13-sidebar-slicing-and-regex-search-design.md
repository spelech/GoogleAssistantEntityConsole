# Design Spec: Sidebar Slicing & Regex Search for Google Assistant Entity Console

- **Date**: 2026-10-13
- **Branch**: `feature/sidebar-slicing-and-regex-search`
- **Target Repository**: `spelech/GoogleAssistantEntityConsole`

---

## 1. Overview
This specification adds a Home Assistant-native 2-pane slicing interface to the Google Assistant Entity Console. It introduces a collapsible left sidebar categorized by Exposure status, Areas/Rooms, and Domains (with dynamic item count badges), an instant regex-capable search engine across names, entity IDs, and aliases, and slice-level breadcrumbs and bulk operations, all while preserving the user's active Home Assistant theme tokens.

---

## 2. Architecture & Layout

### 2.1 Dual-Pane Shell
- **Root Container**: Full `100vh` flexbox shell (`display: flex; height: 100vh; overflow: hidden;`).
- **Collapsible Sidebar (`#sidebar`)**:
  - Desktop width: `260px` flex-shrink `0`.
  - Collapsed state: Width transitions to `0px` (or compact toggle state), setting `display: none` or hiding with CSS transform.
  - Collapse toggle button in top bar and at sidebar header.
  - Responsive behavior: On mobile viewports (`max-width: 768px`), renders as an off-canvas drawer with backdrop overlay scrim.
  - State persistence: Remembers collapsed state in `localStorage.getItem('gaec_sidebar_collapsed')`.
- **Main Pane (`#mainPane`)**:
  - Flex child (`flex: 1; display: flex; flex-direction: column; overflow: hidden;`).
  - Contains KPI stats strip, breadcrumb & slice action bar, sticky table header, and isolated scrollable entity grid.

### 2.2 Slicing Navigation Hierarchy
The sidebar displays three primary sections:
1. **Exposure Status**:
   - `All Entities (total)`
   - `Exposed to Google (count)`
   - `Not Exposed (count)`
   - `Custom Voice Overrides (count)` (entities with custom voice name or aliases)
2. **Areas / Rooms**:
   - Alphabetical list of Home Assistant areas with count badges.
   - Includes `Unassigned Area` for devices without an area.
3. **Domains**:
   - List of domains (`light`, `switch`, `climate`, `cover`, `fan`, `sensor`, etc.) with standard icons and count badges.
4. **Sidebar Filter Input**:
   - Quick text filter at the top of the sidebar allowing users with large setups (30+ areas) to quickly locate an area or domain in the tree.

---

## 3. Search & Regex Engine

### 3.1 Search Matching Logic
- **Fields Evaluated**:
  1. Entity friendly name (`entity.name` or `entity.attributes.friendly_name`)
  2. Entity ID (`entity.entity_id`)
  3. Google Voice Name (`entity.google_name` or `entity.name`)
  4. Voice Aliases (`entity.aliases` array)
  5. Area Name (`entity.area_name`)
- **Regex Support**:
  - Attempts compilation via `new RegExp(query, 'i')`.
  - **Graceful Fallback**: If `new RegExp()` throws a `SyntaxError` (e.g. incomplete group `(living|bed` or bracket `[`), the engine automatically catches the error and executes standard case-insensitive substring `.includes()` matching.
  - **Regex Status Indicator**: An icon badge (`.*`) in the search bar indicates whether a valid regex pattern is currently active.

---

## 4. Slice Scoping & Bulk Actions

### 4.1 Breadcrumb & Slicing Scope
- Clicking any sidebar item sets `activeSlice = { type, value, label, count }`.
- **Breadcrumb Bar**:
  - Displays `Category / Selection (X matches)`.
  - Includes `✕ Clear Slice` button to reset to `All Entities`.
- **Slice Bulk Action**:
  - `Expose All in Slice` / `Unexpose All in Slice` button triggers batch exposure toggle for all entities currently visible in the active slice.

---

## 5. Home Assistant Theme Integrity

- Strict usage of Home Assistant CSS custom properties:
  - `--primary-background-color`: App background.
  - `--card-background-color`: Sidebar background and data grid container.
  - `--secondary-background-color`: Hover rows, sidebar item hover, search input background.
  - `--primary-text-color`: Main headings and entity titles.
  - `--secondary-text-color`: Subtitles, entity IDs, count badges.
  - `--primary-color` / `--accent-color`: Selected sidebar item, active indicators, primary buttons.
  - `--divider-color`: All table borders, dividers, and panel separators.
  - `--success-color` / `--error-color`: Exposure status indicators.
- Live `postMessage` listener for `hass-update` ensures immediate synchronization when HA toggles between dark/light or custom theme modes.

---

## 6. Verification Plan
1. **Pytest Integration Suite**: Run all 342 tests in `tests/` to guarantee no regressions.
2. **Browser Testing (Home Assistant DevTools)**:
   - Verify sidebar collapses and expands properly.
   - Verify clicking Areas, Domains, and Exposure status filters the table accurately.
   - Verify regex search (e.g. `^light\.(living|bed)` or `fan|lamp`) correctly filters matching entities.
   - Verify invalid regexes do not throw console errors and gracefully fall back to substring search.
   - Verify dark and light themes render cleanly using Home Assistant CSS variables.
3. **CI & Screenshots**: Verify GitHub Actions CI passes green and attach screenshots to the PR.
