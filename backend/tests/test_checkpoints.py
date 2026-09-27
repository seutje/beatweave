import io
from pathlib import Path
from urllib.error import URLError

import pytest

from beatweave.analysis import checkpoints
from beatweave.analysis.checkpoints import BeatThisCheckpointStore
from beatweave.errors import BeatweaveError


class DownloadResponse(io.BytesIO):
    def __init__(self, content: bytes, reported_size: int | None = None) -> None:
        super().__init__(content)
        self.headers = {
            "Content-Length": str(reported_size if reported_size is not None else len(content))
        }


def test_checkpoint_is_downloaded_once_and_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def open_checkpoint(*_: object, **__: object) -> DownloadResponse:
        nonlocal calls
        calls += 1
        return DownloadResponse(b"checkpoint-data")

    monkeypatch.setattr(checkpoints, "urlopen", open_checkpoint)
    store = BeatThisCheckpointStore(tmp_path / "models")

    first = store.resolve("final0")
    second = store.resolve("final0")

    assert first == second
    assert first.read_bytes() == b"checkpoint-data"
    assert calls == 1
    assert not first.with_suffix(".ckpt.part").exists()


def test_failed_download_is_reported_and_partial_file_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_download(*_: object, **__: object) -> DownloadResponse:
        raise URLError("offline")

    monkeypatch.setattr(checkpoints, "urlopen", fail_download)
    store = BeatThisCheckpointStore(tmp_path / "models")

    with pytest.raises(BeatweaveError) as raised:
        store.resolve("final0")

    assert raised.value.code == "checkpoint_download_failed"
    assert "offline" in raised.value.message
    assert not (tmp_path / "models" / "beat_this-final0.ckpt.part").exists()


def test_incomplete_download_is_not_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checkpoints,
        "urlopen",
        lambda *_args, **_kwargs: DownloadResponse(b"short", reported_size=20),
    )
    store = BeatThisCheckpointStore(tmp_path / "models")

    with pytest.raises(BeatweaveError, match="incomplete"):
        store.resolve("final0")

    assert not (tmp_path / "models" / "beat_this-final0.ckpt").exists()
