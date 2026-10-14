# Implementation Plan: Sidebar Slicing & Regex Search for Google Assistant Entity Console

- **Date**: 2026-10-13
- **Branch**: `feature/sidebar-slicing-and-regex-search`
- **Target Repository**: `spelech/GoogleAssistantEntityConsole`

---

## Proposed Changes

### 1. `static/index.html`
- Add collapsible sidebar markup (`#sidebar`) inside the main layout wrapper.
- Include sidebar search input (`#sidebarFilterInput`) for quick area/domain lookup.
- Include navigation containers: `#exposureNav`, `#areasNav`, `#domainsNav`.
- Add sidebar toggle button (`#sidebarToggleBtn`) in top app header.
- Add breadcrumb bar (`#breadcrumbBar`) with `#breadcrumbSliceText`, `#clearSliceBtn`, and `#sliceBulkActionBtn`.
- Add regex indicator pill (`#regexIndicator`) in `#searchContainer`.

### 2. `static/style.css`
- Add 2-pane flex layout styles:
  - `#appContainer`: `display: flex; height: 100vh; overflow: hidden;`
  - `#sidebar`: `width: 260px; min-width: 260px; transition: all 0.25s ease; ...`
  - `#sidebar.collapsed`: `width: 0; min-width: 0; padding: 0; border: none; overflow: hidden;`
  - `#mainContentPane`: `flex: 1; display: flex; flex-direction: column; overflow: hidden;`
- Theme sidebar items using `--card-background-color`, `--secondary-background-color`, and `--primary-color`.
- Add responsive drawer styles for viewports `< 768px` with backdrop scrim.
- Add breadcrumb bar and regex badge styles.

### 3. `static/app.js`
- State:
  - `activeSlice: { type: 'all', value: null }`
  - `sidebarCollapsed: false` (loaded from `localStorage`)
- Functions:
  - `renderSidebar()`: Computes dynamic item counts for exposure states, areas, and domains.
  - `setSlice(type, value, label)`: Sets active slice, highlights active sidebar element, updates breadcrumb bar, and refreshes table.
  - `clearSlice()`: Resets slice to `'all'`.
  - `matchesSearch(entity, query)`: Compiles `new RegExp(query, 'i')` or falls back to case-insensitive `.includes()` across name, entity_id, google_name, aliases, and area_name. Updates `#regexIndicator`.
  - `toggleSidebar()`: Toggles `.collapsed` class and persists state.
  - `exposeAllInSlice(expose)`: Batch sets exposure for all entities in the current slice.
- Wire event listeners for sidebar filter, sidebar toggle, breadcrumb actions, and search input.

### 4. `manifest.json`
- Bump version to `1.10.0` for asset cache busting.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/` in repo root. All 342 tests must pass.

### Interactive Live Verification (Home Assistant DevTools)
1. Navigate to Entity Console in Home Assistant browser page.
2. Verify sidebar renders with accurate counts: Exposure states, Areas, Domains.
3. Test Slicing:
   - Click an area (e.g. Living Room) -> Table filters to Living Room, breadcrumb shows `Area / Living Room (X entities)`.
   - Click a domain (e.g. Light) -> Table filters to Light.
   - Click `Exposed Only` -> Table filters to exposed entities.
   - Click `✕ Clear Slice` -> Restores to all entities.
4. Test Regex Search:
   - Type `light\.(living|bed)` -> Filters to matching entities, regex badge highlights.
   - Type invalid regex like `[` -> Falls back to substring match, does not crash or throw unhandled error.
5. Test Sidebar Collapse:
   - Click collapse button -> Sidebar smoothly slides shut, main table fills full width.
   - Reload page -> Sidebar remembers collapsed state from `localStorage`.
6. Theme Check:
   - Verify all elements adapt to Home Assistant theme variables (light/dark mode).

### Release / PR Verification
- Capture screenshots of sidebar slicing and regex search.
- Commit to `feature/sidebar-slicing-and-regex-search` and push to origin.
- Open PR on GitHub and verify CI actions pass 100% green.
- Attach screenshots to PR description.
