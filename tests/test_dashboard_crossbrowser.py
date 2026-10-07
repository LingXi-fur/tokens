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
    test_theme_url_first_frame = (
        runtime.DashboardRuntimeTests.test_url_theme_first_frame_and_saved_preference
    )
    test_other_model_names = (
        runtime.DashboardRuntimeTests.test_other_model_names_match_windows_and_escape_html
    )
    test_other_zero_net_change = (
        runtime.DashboardRuntimeTests.test_other_zero_net_change_keeps_model_churn_visible
    )
    test_other_evidence_guard = (
        runtime.DashboardRuntimeTests.test_other_change_has_no_misleading_project_evidence_button
    )
    test_mouse_drag_interval = (
        runtime.DashboardRuntimeTests.test_mouse_drag_selects_a_then_click_selects_b
    )

    interval_url = runtime.DashboardRuntimeTests.interval_url
    interval_snapshot = runtime.DashboardRuntimeTests.interval_snapshot
    click_bar = runtime.DashboardRuntimeTests.click_bar
    test_delta_evidence_exact_windows = (
        runtime.DashboardRuntimeTests.test_delta_evidence_exact_windows_keyboard_navigation_and_privacy
    )
    test_delta_evidence_english_and_escape = (
        runtime.DashboardRuntimeTests.test_delta_evidence_partial_missing_english_escape_and_project_lens
    )
    test_delta_evidence_mobile_geometry = (
        runtime.DashboardRuntimeTests.test_delta_evidence_mobile_geometry
    )
    test_delta_evidence_project_navigation = (
        runtime.DashboardRuntimeTests.test_delta_evidence_project_navigation_preserves_global_filters
    )
    test_delta_evidence_open_period = (
        runtime.DashboardRuntimeTests.test_delta_evidence_uses_open_period_elapsed_days
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
