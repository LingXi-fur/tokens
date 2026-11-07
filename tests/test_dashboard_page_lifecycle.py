"""Failure ownership contracts for the real synthetic browser page helpers."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.verify_dashboard import BrowserSafetyStop
from tests.test_dashboard_cost_actions import ActionsPageMixin
from tests import test_dashboard_runtime as runtime


HELPERS = (ActionsPageMixin.new_page, runtime.DashboardRuntimeTests.new_page)


def fixture(helper, *, close_error=None):
    page = mock.Mock()
    context = mock.Mock()
    browser = mock.Mock()
    browser.new_context.return_value = context
    context.new_page.return_value = page
    context.close.side_effect = close_error
    owner = SimpleNamespace(_browser=browser, _page=Path('/synthetic/cost.html'),
                            _path=Path('/synthetic/runtime.html'))
    return owner, browser, context, page


class DashboardPageLifecycleTests(unittest.TestCase):
    def test_success_transfers_context_and_preserves_launch_options(self):
        for helper in HELPERS:
            with self.subTest(helper=helper.__qualname__):
                owner, browser, context, page = fixture(helper)
                result = helper(owner)
                self.assertIs(context, result[0])
                self.assertIs(page, result[1])
                self.assertEqual(([], []), result[2:])
                context.close.assert_not_called()
                expected = dict(viewport={'width': 1280, 'height': 820},
                                color_scheme='light', reduced_motion='no-preference')
                if helper is ActionsPageMixin.new_page:
                    expected['accept_downloads'] = True
                browser.new_context.assert_called_once_with(**expected)
                path = owner._page if helper is ActionsPageMixin.new_page else owner._path
                page.goto.assert_called_once_with(path.as_uri(), wait_until='load')
                self.assertEqual(['pageerror', 'console'], [call.args[0] for call in page.on.call_args_list])
                context.close()
                context.close.assert_called_once_with()

    def test_context_creation_failure_propagates_without_closing(self):
        for helper in HELPERS:
            with self.subTest(helper=helper.__qualname__):
                owner, browser, context, page = fixture(helper)
                error = RuntimeError('synthetic context creation')
                browser.new_context.side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    helper(owner)
                self.assertIs(error, caught.exception)
                context.close.assert_not_called()
                context.new_page.assert_not_called()

    def test_each_initialization_failure_closes_before_propagating(self):
        for helper in HELPERS:
            stages = ('page', 'pageerror', 'console', 'goto')
            if helper is runtime.DashboardRuntimeTests.new_page:
                stages += ('script',)
            for stage in stages:
                with self.subTest(helper=helper.__qualname__, stage=stage):
                    owner, browser, context, page = fixture(helper)
                    error = RuntimeError('synthetic ' + stage)
                    if stage == 'page':
                        context.new_page.side_effect = error
                    elif stage in ('pageerror', 'console'):
                        def on(name, callback):
                            if name == stage:
                                raise error
                        page.on.side_effect = on
                    elif stage == 'script':
                        page.add_init_script.side_effect = error
                    else:
                        page.goto.side_effect = error
                    options = {'freeze_lazy': True} if stage == 'script' else {}
                    with self.assertRaises(RuntimeError) as caught:
                        helper(owner, **options)
                    self.assertIs(error, caught.exception)
                    context.close.assert_called_once_with()

    def test_secondary_close_failure_never_replaces_initialization_error(self):
        for helper in HELPERS:
            for error in (RuntimeError('synthetic navigation'), KeyboardInterrupt(),
                          BrowserSafetyStop('synthetic safety stop')):
                with self.subTest(helper=helper.__qualname__, error=type(error).__name__):
                    owner, browser, context, page = fixture(helper, close_error=RuntimeError('synthetic close'))
                    page.goto.side_effect = error
                    with self.assertRaises(type(error)) as caught:
                        helper(owner)
                    self.assertIs(error, caught.exception)
                    context.close.assert_called_once_with()

    def test_runtime_custom_path_and_frozen_lazy_options_are_preserved(self):
        helper = runtime.DashboardRuntimeTests.new_page
        owner, browser, context, page = fixture(helper)
        result = helper(owner, path='http://127.0.0.1/synthetic', freeze_lazy=True,
                        viewport={'width': 390, 'height': 820},
                        color_scheme='dark', reduced_motion='reduce')
        self.assertIs(context, result[0])
        page.add_init_script.assert_called_once()
        self.assertIn('FrozenIntersectionObserver', page.add_init_script.call_args.args[0])
        page.goto.assert_called_once_with('http://127.0.0.1/synthetic', wait_until='load')
        browser.new_context.assert_called_once_with(viewport={'width': 390, 'height': 820},
                                                   color_scheme='dark', reduced_motion='reduce')
        context.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
