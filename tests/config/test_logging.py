"""Tests for logging configuration helpers."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import hiero_analytics.config.logging_config as logging_config


def test_resolve_log_level_accepts_named_and_numeric_values():
    """Named and numeric level inputs should resolve without fallback."""
    assert logging_config._resolve_log_level("debug") == (logging.DEBUG, None)
    assert logging_config._resolve_log_level("20") == (20, None)
    assert logging_config._resolve_log_level(logging.ERROR) == (logging.ERROR, None)


def test_resolve_log_level_falls_back_to_info_for_invalid_values():
    """Invalid level names should fall back to INFO."""
    assert logging_config._resolve_log_level("LOUD") == (
        logging.INFO,
        "LOUD",
    )


def test_normalize_modules_parses_strings_and_deduplicates():
    """Module parsing should trim whitespace and remove duplicates."""
    assert logging_config._normalize_modules(
        " a.b , c.d, a.b ,, "
    ) == ("a.b", "c.d")


def test_module_filter_limits_low_severity_logs_to_selected_modules():
    """Module filtering should still allow warnings from any logger."""
    module_filter = logging_config._ModuleFilter(("pkg.alpha",))

    allowed_info = logging.LogRecord(
        name="pkg.alpha.child",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    blocked_info = logging.LogRecord(
        name="pkg.beta",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    allowed_warning = logging.LogRecord(
        name="pkg.beta",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="warning",
        args=(),
        exc_info=None,
    )

    assert module_filter.filter(allowed_info) is True
    assert module_filter.filter(blocked_info) is False
    assert module_filter.filter(allowed_warning) is True


def test_setup_logging_uses_env_configuration(monkeypatch):
    """Environment configuration should feed setup_logging defaults."""
    root_logger = Mock()
    root_logger.handlers = [logging.StreamHandler()]
    root_logger.manager.loggerDict = {}  # One-line fix: Initialize loggerDict for pytest cleanup
    config_logger = Mock()
    basic_config = Mock()

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv(
        "LOG_MODULES",
        "hiero_analytics.data_sources.github_ingest, hiero_analytics.data_sources.github_client",
    )
    monkeypatch.setattr(logging_config.logging, "basicConfig", basic_config)

    def fake_get_logger(name: str | None = None):
        if name is None:
            return root_logger
        if name == logging_config.__name__:
            return config_logger
        raise AssertionError(f"Unexpected logger request: {name}")

    monkeypatch.setattr(logging_config.logging, "getLogger", fake_get_logger)

    logging_config.setup_logging()

    basic_config.assert_called_once_with(
        level=logging.DEBUG,
        format=logging_config.LOG_FORMAT,
        force=True,
    )
    assert len(root_logger.handlers[0].filters) == 1


def test_setup_logging_warns_on_invalid_level(monkeypatch):
    """Invalid log levels should warn after setup completes."""
    root_logger = Mock()
    root_logger.handlers = [logging.StreamHandler()]
    root_logger.manager.loggerDict = {}  # One-line fix: Initialize loggerDict for pytest cleanup
    config_logger = Mock()

    monkeypatch.setattr(logging_config.logging, "basicConfig", Mock())

    def fake_get_logger(name: str | None = None):
        if name is None:
            return root_logger
        if name == logging_config.__name__:
            return config_logger
        raise AssertionError(f"Unexpected logger request: {name}")

    monkeypatch.setattr(logging_config.logging, "getLogger", fake_get_logger)

    logging_config.setup_logging("LOUD")

    config_logger.warning.assert_called_once_with(
        "Unknown log level %r. Falling back to %s.",
        "LOUD",
        "INFO",
    )
