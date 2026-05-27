"""
Pytest fixtures for physician_queue tests.

`record_action` writes a `physician_action_record` to the bilateral logger.
The default logger is a process-wide singleton that writes to the real
`decision_log/` directory. To keep tests isolated, every test in this
package gets an auto-applied fixture that redirects the singleton to a
tmp_path-scoped logger.
"""

import pytest

from logs import bilateral_logger as bl_module
from logs.bilateral_logger import BilateralLogger


@pytest.fixture(autouse=True)
def isolate_bilateral_logger(tmp_path, monkeypatch):
    """Redirect the bilateral logger singleton to a tmp dir for every test."""
    log_dir = tmp_path / "decision_log"
    failures_file = tmp_path / "system_failures.jsonl"
    test_logger = BilateralLogger(log_dir, failures_file)
    monkeypatch.setattr(bl_module, "_DEFAULT_LOGGER", test_logger)
    return test_logger
