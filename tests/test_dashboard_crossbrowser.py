import os
import unittest

try:
    from tests import test_dashboard_runtime as runtime
except ImportError:
    import test_dashboard_runtime as runtime


@unittest.skipIf(runtime.sync_playwright is None, "Playwright is not installed")
class DashboardCrossBrowserTests(unittest.TestCase):
    """Focused geometry/interaction contracts in the requested browser engine."""

    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")
    setUpClass = classmethod(runtime.DashboardRuntimeTests.setUpClass.__func__)
    tearDownClass = classmethod(runtime.DashboardRuntimeTests.tearDownClass.__func__)
    new_page = runtime.DashboardRuntimeTests.new_page

    test_table_sort_tri_state = (
        runtime.DashboardRuntimeTests.test_table_sort_cycles_three_states_and_returns_to_time_order
    )
    test_model_column_sort_tri_state = (
        runtime.DashboardRuntimeTests.test_model_column_sort_cycles_safely_and_resets_when_filtered
    )
    test_achievement_archive_direct_url = (
        runtime.DashboardRuntimeTests.test_achievement_archive_direct_url_history_and_details
    )
    test_achievement_archive_mobile_geometry = (
        runtime.DashboardRuntimeTests.test_achievement_archive_copy_and_mobile_geometry
    )
    test_donut_legend_sync = (
        runtime.DashboardRuntimeTests.test_donut_legend_syncs_surfaces_and_recovers_from_all_off
    )
    test_layout_without_horizontal_overflow = (
        runtime.DashboardRuntimeTests.test_mobile_table_detail_expands_without_horizontal_overflow
    )
    test_faint_contrast_meets_aa = (
        runtime.DashboardRuntimeTests.test_faint_color_contrast_meets_aa_in_both_themes
    )

    def test_row_keyboard_flow(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#tabs [data-gran="day"]').click()
            rows = page.locator("#tbody tr[data-period]")
            rows.first.focus()
            page.keyboard.press("ArrowDown")
            period = page.locator("#tbody tr[data-period]:focus").get_attribute("data-period")
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(1, page.locator("#bar .barstack.scrub-preview").count())
            page.keyboard.press("Enter")
            self.assertEqual(
                period,
                page.locator("#tbody tr.row-focused").get_attribute("data-period"),
            )
            page.keyboard.press("Escape")
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(0, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()
