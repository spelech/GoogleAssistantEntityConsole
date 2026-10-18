"""End-to-End Playwright test suite for Google Assistant Entity Console frontend.

Tests cover:
- Slicing sidebar multi-section stacked filtering (Exposure + Area + Domain)
- Dynamic breadcrumb chips and single-chip removal
- Combined search syntax specifiers (not:exposed, is:unexposed, area:, domain:)
- Regex search and regex indicator badge
- Sidebar collapse/expand toggle
- Dynamic bulk action button
"""

import http.server
import json
import threading
from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="playwright is not installed in the environment",
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "google_assistant_entity_console" / "static"

SAMPLE_ENTITIES = [
    {
        "entity_id": "light.basement_ceiling",
        "name": "Basement Ceiling",
        "domain": "light",
        "area": "Basement",
        "should_expose": False,
        "aliases": [],
    },
    {
        "entity_id": "light.basement_lamp",
        "name": "Basement Lamp",
        "domain": "light",
        "area": "Basement",
        "should_expose": True,
        "aliases": ["Desk Lamp"],
    },
    {
        "entity_id": "switch.basement_fan",
        "name": "Basement Fan",
        "domain": "switch",
        "area": "Basement",
        "should_expose": False,
        "aliases": [],
    },
    {
        "entity_id": "light.living_room_lamp",
        "name": "Living Room Lamp",
        "domain": "light",
        "area": "Living Room",
        "should_expose": True,
        "aliases": [],
    },
    {
        "entity_id": "switch.kitchen_plug",
        "name": "Kitchen Plug",
        "domain": "switch",
        "area": "Kitchen",
        "should_expose": False,
        "aliases": [],
    },
    {
        "entity_id": "sensor.unassigned_temp",
        "name": "Unassigned Sensor",
        "domain": "sensor",
        "area": None,
        "should_expose": False,
        "aliases": [],
    },
]


class StaticHttpServer:
    """Lightweight threaded HTTP server serving static frontend files."""

    def __init__(self, directory: Path):
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(directory), **kwargs)

            def log_message(self, format, *args):
                pass  # Suppress request logging during tests

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()


@pytest.fixture(scope="module")
def static_server():
    """Start static server for the module duration."""
    server = StaticHttpServer(STATIC_DIR)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def page(static_server):
    """Launch headless browser and navigate to console with mocked entities."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium browser could not be launched: {e}")

        context = browser.new_context(viewport={"width": 1280, "height": 800})
        pg = context.new_page()

        # Intercept /entities endpoint
        pg.route(
            "**/api/google_assistant_entity_console/entities",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "entities": SAMPLE_ENTITIES,
                    "version": "2.0.0",
                    "yaml_filename": "configuration.yaml",
                }),
            ),
        )

        # Mock AI settings endpoint to prevent 404 console errors
        pg.route(
            "**/api/google_assistant_entity_console/ai/settings",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({}),
            ),
        )

        # Mock Google settings endpoint
        pg.route(
            "**/api/google_assistant_entity_console/google_settings",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "google_settings": {
                        "project_id": "test-home-proj",
                        "report_state": True,
                        "secure_devices_pin": "1234",
                        "auto_sync": True,
                        "has_service_account": True,
                        "client_email": "ga-sync@test-home-proj.iam.gserviceaccount.com",
                    },
                    "runtime": {
                        "mode": "storage",
                        "project_id": "test-home-proj",
                        "has_service_account": True,
                        "is_reporting_state": True,
                        "agent_users_count": 1,
                    },
                    "has_legacy_yaml": True,
                }),
            ),
        )

        url = f"http://127.0.0.1:{static_server.port}/index.html"
        pg.goto(url)
        pg.wait_for_selector("#entityTableBody tr.entity-row")

        yield pg

        context.close()
        browser.close()


def test_initial_load(page):
    """Test initial rendering of entities and sidebar statistics."""
    rows = page.locator("#entityTableBody tr.entity-row").count()
    assert rows == 6

    # Verify counts in sidebar
    count_all = page.locator("#countAll").text_content()
    assert count_all == "6"

    count_exposed = page.locator("#countExposed").text_content()
    assert count_exposed == "2"

    count_unexposed = page.locator("#countUnexposed").text_content()
    assert count_unexposed == "4"


def test_stacked_sidebar_filtering_and_breadcrumbs(page):
    """Test stacking exposure, area, and domain filters, and removing chips individually."""
    # 1. Filter: Not Exposed
    page.click('[data-slice-value="unexposed"]')
    page.wait_for_timeout(200)

    unexposed_chips = page.locator(".breadcrumb-chip").all_text_contents()
    assert len(unexposed_chips) == 1
    assert "Not Exposed" in unexposed_chips[0]
    assert page.locator("#entityTableBody tr.entity-row").count() == 4

    # 2. Stack Area: Basement
    page.click('[data-filter-type="area"][data-filter-value="Basement"]')
    page.wait_for_timeout(200)

    chips = page.locator(".breadcrumb-chip").all_text_contents()
    assert len(chips) == 2
    assert any("Not Exposed" in c for c in chips)
    assert any("Basement" in c for c in chips)
    # Basement has 3 entities (2 unexposed: ceiling, fan; 1 exposed: lamp)
    assert page.locator("#entityTableBody tr.entity-row").count() == 2

    # 3. Stack Domain: light
    page.click('[data-filter-type="domain"][data-filter-value="light"]')
    page.wait_for_timeout(200)

    chips = page.locator(".breadcrumb-chip").all_text_contents()
    assert len(chips) == 3
    # Only light.basement_ceiling matches (unexposed + Basement + light)
    assert page.locator("#entityTableBody tr.entity-row").count() == 1

    # 4. Remove Domain chip
    page.click('.breadcrumb-chip[data-filter-type="domain"] .chip-remove')
    page.wait_for_timeout(200)

    chips = page.locator(".breadcrumb-chip").all_text_contents()
    assert len(chips) == 2
    assert page.locator("#entityTableBody tr.entity-row").count() == 2

    # 5. Clear all filters via button
    page.click("#clearSliceBtn")
    page.wait_for_timeout(200)

    assert page.locator(".breadcrumb-chip").count() == 0
    assert page.locator("#entityTableBody tr.entity-row").count() == 6


def test_search_syntax_specifiers(page):
    """Test search syntax specifiers like not:exposed, area:, domain:."""
    # not:exposed basement
    page.fill("#searchInput", "not:exposed basement")
    page.wait_for_timeout(300)
    assert page.locator("#entityTableBody tr.entity-row").count() == 2

    # is:unexposed domain:light
    page.fill("#searchInput", "is:unexposed domain:light")
    page.wait_for_timeout(300)
    assert page.locator("#entityTableBody tr.entity-row").count() == 1

    # is:exposed area:living
    page.fill("#searchInput", "is:exposed area:living")
    page.wait_for_timeout(300)
    assert page.locator("#entityTableBody tr.entity-row").count() == 1

    # has:alias
    page.fill("#searchInput", "has:alias")
    page.wait_for_timeout(300)
    assert page.locator("#entityTableBody tr.entity-row").count() == 1

    # Clear search
    page.fill("#searchInput", "")
    page.wait_for_timeout(200)
    assert page.locator("#entityTableBody tr.entity-row").count() == 6


def test_regex_search(page):
    """Test regex pattern matching across entity IDs and indicator badge."""
    page.fill("#searchInput", r"light\..*lamp")
    page.wait_for_timeout(300)

    # Matches light.basement_lamp and light.living_room_lamp
    assert page.locator("#entityTableBody tr.entity-row").count() == 2
    assert page.locator("#regexIndicator").is_visible() is True

    # Clear search and verify regex badge disappears
    page.fill("#searchInput", "")
    page.wait_for_timeout(200)
    assert page.locator("#regexIndicator").is_visible() is False


def test_sidebar_toggle(page):
    """Test sidebar collapse and expand toggle behavior."""
    sidebar = page.locator("#appSidebar")
    is_collapsed = "collapsed" in (sidebar.get_attribute("class") or "")
    assert not is_collapsed

    # Click collapse button
    page.click("#sidebarCollapseBtn")
    page.wait_for_timeout(200)

    is_collapsed_after = "collapsed" in (sidebar.get_attribute("class") or "")
    assert is_collapsed_after is True

    # Click expand toggle button
    page.click("#sidebarToggleBtn")
    page.wait_for_timeout(200)

    is_collapsed_final = "collapsed" in (sidebar.get_attribute("class") or "")
    assert is_collapsed_final is False


def test_bulk_action_button_dynamic_text(page):
    """Test that the bulk action button dynamically updates text and count based on filter."""
    bulk_btn = page.locator("#sliceBulkActionBtn")
    bulk_text = page.locator("#sliceBulkActionText")

    # Initially hidden when no filters active
    assert not bulk_btn.is_visible()

    # Filter to Not Exposed + Basement
    page.click('[data-slice-value="unexposed"]')
    page.click('[data-filter-type="area"][data-filter-value="Basement"]')
    page.wait_for_timeout(200)

    assert bulk_btn.is_visible()
    assert "Expose All in Filter (2)" in (bulk_text.text_content() or "")

    # Clear filters
    page.click("#clearSliceBtn")
    page.wait_for_timeout(200)
    assert not bulk_btn.is_visible()


def test_sidebar_category_filter_input(page):
    """Test filtering categories inside the sidebar using the quick filter input."""
    # Filter areas by typing 'base'
    page.fill("#sidebarFilterInput", "base")
    page.wait_for_timeout(200)

    visible_areas = page.locator("#areasNav .sidebar-item").all_text_contents()
    assert len(visible_areas) == 1
    assert "Basement" in visible_areas[0]

    # Clear sidebar filter input
    page.fill("#sidebarFilterInput", "")
    page.wait_for_timeout(200)

    all_areas = page.locator("#areasNav .sidebar-item").all_text_contents()
    assert len(all_areas) >= 3


def test_unassigned_area_filter(page):
    """Test slicing by unassigned area."""
    page.click('[data-filter-type="area"][data-filter-value="__unassigned__"]')
    page.wait_for_timeout(200)

    chips = page.locator(".breadcrumb-chip").all_text_contents()
    assert len(chips) == 1
    assert "Unassigned" in chips[0]

    rows = page.locator("#entityTableBody tr.entity-row").count()
    assert rows == 1
    assert "sensor.unassigned_temp" in (page.locator("#entityTableBody").text_content() or "")


def test_live_sync_to_google_without_restart_modal(page):
    """Test clicking Sync to Google calls /sync and does not open the restart modal."""
    sync_called = []

    def handle_sync(route):
        sync_called.append(True)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "success": True,
                "status_code": 200,
                "exposed_count": 2,
                "agent_users_count": 1,
                "mode": "storage",
                "synced_offline": False,
            }),
        )

    page.route("**/api/google_assistant_entity_console/sync", handle_sync)

    btn_text = page.locator("#rebuildBtn").text_content() or ""
    assert "Sync to Google" in btn_text

    page.click("#rebuildBtn")
    page.wait_for_timeout(300)

    assert len(sync_called) == 1
    # Restart modal must NOT open on live sync
    assert page.locator("#restartModal").is_visible() is False
    assert "Synced 2 entities" in (page.locator("#toast").text_content() or "")


def test_google_storage_settings_and_yaml_migration(page):
    """Test viewing/saving Google Assistant .storage credentials and migrating from YAML."""
    saved_payloads = []
    migrated = []

    def handle_google_settings(route):
        if route.request.method == "POST":
            saved_payloads.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "google_settings": {
                        "project_id": "new-storage-proj",
                        "report_state": True,
                        "secure_devices_pin": "5678",
                        "auto_sync": False,
                        "has_service_account": True,
                        "client_email": "ga-sync@test-home-proj.iam.gserviceaccount.com",
                    },
                    "runtime": {
                        "mode": "storage",
                        "project_id": "new-storage-proj",
                        "has_service_account": True,
                        "is_reporting_state": True,
                        "agent_users_count": 1,
                    },
                    "has_legacy_yaml": True,
                }),
            )
        else:
            route.continue_()

    def handle_migrate_yaml(route):
        migrated.append(True)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "migrated": True,
                "yaml_commented_out": True,
                "project_id": "test-home-proj",
                "has_service_account": True,
                "runtime": {"mode": "storage"},
            }),
        )

    page.route("**/api/google_assistant_entity_console/google_settings", handle_google_settings)
    page.route("**/api/google_assistant_entity_console/migrate_yaml", handle_migrate_yaml)

    # Open Settings modal
    page.click("#openAiSettingsBtn")
    page.wait_for_timeout(200)

    # Check pre-populated Google Assistant .storage fields
    assert page.input_value("#gaProjectIdInput") == "test-home-proj"
    assert page.input_value("#gaPinInput") == "1234"
    assert page.is_checked("#gaReportStateToggle") is True
    assert page.is_checked("#gaAutoSyncToggle") is True
    assert "ga-sync@test-home-proj.iam.gserviceaccount.com" in (
        page.locator("#gaServiceAccountStatus").text_content() or ""
    )

    # Trigger one-click Migrate from YAML
    assert page.locator("#migrateYamlBtn").is_visible() is True
    page.click("#migrateYamlBtn")
    page.wait_for_timeout(200)
    assert len(migrated) == 1

    # Export to YAML for standalone rollback / clean uninstall
    exported = []
    page.route(
        "**/api/google_assistant_entity_console/rebuild",
        lambda route: (
            exported.append(True),
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "success": True,
                    "filename": "gaGen_101726.yaml",
                    "exposed_count": 2,
                    "has_include_directive": False,
                    "required_include": "google_assistant: !include gaGen_101726.yaml",
                }),
            ),
        ),
    )

    assert page.locator("#exportYamlBtn").is_visible() is True
    page.click("#exportYamlBtn")
    page.wait_for_timeout(300)
    assert len(exported) == 1
    assert "Exported 2 entities to gaGen_101726.yaml" in (page.locator("#toast").text_content() or "")

    # Update Google settings and save
    page.fill("#gaProjectIdInput", "new-storage-proj")
    page.fill("#gaPinInput", "5678")
    page.uncheck("#gaAutoSyncToggle")
    page.click("#saveAiSettingsBtn")
    page.wait_for_timeout(300)

    assert len(saved_payloads) == 1
    assert saved_payloads[0]["project_id"] == "new-storage-proj"
    assert saved_payloads[0]["secure_devices_pin"] == "5678"
    assert saved_payloads[0]["auto_sync"] is False


def test_ha_drawer_sidebar_frame_containment(static_server):
    """Verify google-assistant-entity-console-panel stays strictly inside ha-drawer .app-content and does not bleed beneath the 256px sidebar."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium browser could not be launched: {e}")

        context = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = context.new_page()
        panel_js = (STATIC_DIR / "panel.js").read_text(encoding="utf-8")

        pg.set_content(
            """
            <!DOCTYPE html>
            <html>
              <head>
                <style>
                  html, body { margin: 0; padding: 0; width: 100%; height: 100%; }
                  .layout { height: 100%; }
                  .sidebar-shell {
                    width: 256px;
                    height: 100%;
                    position: fixed;
                    left: 0;
                    top: 0;
                    z-index: 6;
                  }
                  .app-content {
                    overflow: unset;
                    min-width: 0;
                    box-sizing: border-box;
                    width: 100%;
                    height: 100%;
                    padding-inline-start: 256px;
                  }
                  ha-panel-custom {
                    display: block;
                    box-sizing: border-box;
                  }
                </style>
              </head>
              <body>
                <div class="layout">
                  <div class="sidebar-shell" id="haSidebar"></div>
                  <div class="app-content" id="haAppContent">
                    <ha-panel-custom id="haPanelCustom"></ha-panel-custom>
                  </div>
                </div>
              </body>
            </html>
            """
        )
        pg.add_script_tag(content=panel_js)
        rect = pg.evaluate(
            """() => {
                const container = document.getElementById("haPanelCustom");
                const el = document.createElement("google-assistant-entity-console-panel");
                container.appendChild(el);
                const r = el.getBoundingClientRect();
                return { x: r.x, y: r.y, width: r.width, height: r.height, position: getComputedStyle(el).position };
            }"""
        )
        assert rect["position"] == "relative"
        assert rect["x"] == 256
        assert rect["width"] == 1184
        assert rect["height"] == 900

        context.close()
        browser.close()



