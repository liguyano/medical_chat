import json
import logging

from app.services.voice_diagnostics import log_voice_event, setup_voice_diagnostics


def test_diagnostics_persist_only_allowed_metadata(tmp_path):
    path = tmp_path / "voice.jsonl"
    handler = setup_voice_diagnostics(path)
    try:
        log_voice_event(
            "upstream_error",
            session_id="SESS-TEST",
            connection_id="voice-test",
            provider_code="invalid_request",
            audio="SECRET_AUDIO",
            instructions="SECRET_PROMPT",
            message="SECRET_PATIENT",
            api_key="SECRET_KEY",
        )
        handler.flush()
        content = path.read_text(encoding="utf-8")
        event = json.loads(content)
        assert event["event"] == "upstream_error"
        assert event["session_id"] == "SESS-TEST"
        assert event["provider_code"] == "invalid_request"
        assert "SECRET" not in content
        assert event["time"]
    finally:
        logging.getLogger("medical.voice.diagnostics").removeHandler(handler)
        handler.close()


def test_diagnostics_file_failure_does_not_block_startup(monkeypatch, tmp_path):
    import app.services.voice_diagnostics as diagnostics

    def denied(*_args, **_kwargs):
        raise PermissionError("no file access")

    monkeypatch.setattr(diagnostics, "RotatingFileHandler", denied)
    assert diagnostics.setup_voice_diagnostics(tmp_path / "voice.jsonl") is None
    diagnostics.log_voice_event("file_unavailable", session_id="SESS-TEST")
