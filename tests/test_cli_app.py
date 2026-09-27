from __future__ import annotations

from dataclasses import replace

import src.cli_app as cli_app
from src.cli_app import Application
from src.config import default_config

from tests.conftest import FakeAdapter


def test_agent_setup_failure_does_not_block_processing_worker(tmp_path, monkeypatch):
    def fail_agent_setup(*_args, **_kwargs):
        raise ValueError("invalid project catalog")

    monkeypatch.setattr(cli_app, "FeedbackAgentWorker", fail_agent_setup)
    config = replace(default_config(), data_root=tmp_path, sarvam_api_key="test-key")
    app = Application(config=config, adapter=FakeAdapter())

    app.start(start_capture=False)
    try:
        assert app._worker is not None  # noqa: SLF001
    finally:
        app.close()
