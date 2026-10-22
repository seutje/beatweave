from pathlib import Path
from types import SimpleNamespace

import pytest

from beatweave.wan2gp.adapter import Wan2GPAdapter
from beatweave.wan2gp.schemas import Wan2GPConfig
from test_wan2gp import completed_job

EXPECTED = "beatweave_scene_11_22dc6dd6-e913-4922-b21a-a92b3cedc295"


@pytest.mark.parametrize("api_name", ["/refresh_gallery", "/finalize_generation_with_state"])
@pytest.mark.parametrize("remote", [False, True])
def test_gallery_matches_truncated_job_before_importing_or_downloading(
    tmp_path: Path, api_name: str, remote: bool
) -> None:
    unrelated = tmp_path / "previous-job.mp4"
    unrelated.write_bytes(b"old-video")
    selected = tmp_path / f"{EXPECTED[:50]}.mp4"
    if not remote:
        selected.write_bytes(b"matching-video")
    remote_file = {
        "path": f"/remote/outputs/{selected.name}",
        "orig_name": selected.name,
        "meta": {"_type": "gradio.FileData"},
    }
    file_data = remote_file if remote else {"path": str(selected)}
    gallery = (0, [{"video": {"path": str(unrelated)}}, {"video": file_data}])
    downloads, reports = [], []

    class Endpoint:
        def download_files(self, data):
            # No older or unrelated gallery item may reach the downloader.
            assert data == [remote_file]
            downloads.append(data)
            selected.write_bytes(b"downloaded-video")
            return ([str(selected)],)

    client = SimpleNamespace(
        download_files=tmp_path,
        submit=lambda *, api_name: completed_job(gallery),
        _infer_fn_index=lambda *_: 1,
        endpoints={1: Endpoint()},
    )
    context = SimpleNamespace(
        check_cancelled=lambda: None,
        report=lambda *args: reports.append(args),
    )
    saved = {"wan2gp_output_filename": EXPECTED}
    adapter = Wan2GPAdapter(Wan2GPConfig())
    result = adapter._read_gallery(client, api_name, context, saved)
    assert adapter._video_paths(result) == [selected]
    assert len(downloads) == int(remote)
    assert client.download_files == tmp_path
    if remote:
        assert "wan2gp_remote_output_directory" not in saved
    else:
        assert saved["wan2gp_remote_output_directory"] == str(tmp_path)


def test_gallery_without_matching_job_does_not_download_or_learn_another_directory(
    tmp_path: Path,
) -> None:
    unrelated = tmp_path / "another-job.mp4"
    unrelated.touch()
    client = SimpleNamespace(
        download_files=tmp_path,
        submit=lambda **_: completed_job([{"video": {"path": str(unrelated)}}]),
    )
    context = SimpleNamespace(check_cancelled=lambda: None)
    saved = {"wan2gp_output_filename": EXPECTED}
    assert Wan2GPAdapter(Wan2GPConfig())._refresh_gallery(client, context, saved) == []
    assert "wan2gp_remote_output_directory" not in saved
    assert client.download_files == tmp_path


def test_output_matching_accepts_only_exact_names_or_wangp_fifty_character_truncation() -> None:
    matches = Wan2GPAdapter._matches_output
    assert matches(f"C:\\remote\\{EXPECTED[:50]}.mp4", EXPECTED)
    assert matches(f"/remote/{EXPECTED}.mp4", EXPECTED)
    assert not matches(f"/remote/{EXPECTED[:49]}.mp4", EXPECTED)
    assert not matches(f"/remote/{EXPECTED[:50]}_other.mp4", EXPECTED)
    assert not matches(f"/remote/{EXPECTED[:50]}.png", EXPECTED)
    assert not matches("/remote/another-job.mp4", EXPECTED)
    assert not matches("/remote/short.mp4", "short-name")
