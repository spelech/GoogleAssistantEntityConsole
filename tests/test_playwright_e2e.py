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

