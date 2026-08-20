from pathlib import Path

from app.services.dialog_audio_store import DialogAudioStore


def test_save_wav_writes_browser_playable_pcm16(tmp_path: Path):
    store = DialogAudioStore(tmp_path)
    url = store.save_wav(
        session_no="S-001",
        generation_id="G-001",
        filename="answer.wav",
        data=b"\x01\x00\x02\x00",
        sample_rate=24_000,
    )

    path = store.resolve(
        session_no="S-001",
        generation_id="G-001",
        filename="answer.wav",
    )
    assert url.endswith("/api/dialog/S-001/audio/G-001/answer.wav")
    assert path.read_bytes()[:4] == b"RIFF"
    assert path.read_bytes()[8:12] == b"WAVE"
    assert path.read_bytes()[-4:] == b"\x01\x00\x02\x00"


def test_resolve_sanitizes_path_traversal(tmp_path: Path):
    store = DialogAudioStore(tmp_path)
    store.save(
        session_no="S-001",
        generation_id="G-001",
        filename="answer.pcm",
        data=b"audio",
    )

    path = store.resolve(
        session_no="S-001/../../outside",
        generation_id="G-001",
        filename="answer.pcm",
    )
    assert path.parent == (tmp_path / "S-001_____outside" / "G-001").resolve()
