import re
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from beatweave.errors import BeatweaveError

CHECKPOINT_BASE_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp"
CHECKPOINT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
DOWNLOAD_LOCK = threading.Lock()


class BeatThisCheckpointStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def resolve(self, model: str) -> Path:
        explicit_path = Path(model).expanduser()
        if explicit_path.is_file():
            return explicit_path.resolve()
        if not CHECKPOINT_NAME.fullmatch(model):
            raise BeatweaveError(
                "invalid_beat_model",
                "The Beat This model must be an official model name or an existing file.",
                status_code=422,
            )

        target = self.directory / f"beat_this-{model}.ckpt"
        with DOWNLOAD_LOCK:
            if target.is_file() and target.stat().st_size > 0:
                return target
            self._download(model, target)
        return target

    def _download(self, model: str, target: Path) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(f"{target.suffix}.part")
        partial.unlink(missing_ok=True)
        url = f"{CHECKPOINT_BASE_URL}/{model}.ckpt"
        request = Request(url, headers={"User-Agent": "Beatweave/0.1"})
        try:
            with urlopen(request, timeout=120) as response, partial.open("xb") as output:
                expected_size = response.headers.get("Content-Length")
                downloaded = 0
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
            if downloaded == 0 or (expected_size is not None and downloaded != int(expected_size)):
                raise OSError("The checkpoint download was incomplete.")
            partial.replace(target)
        except (HTTPError, URLError, OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            raise BeatweaveError(
                "checkpoint_download_failed",
                f"Could not download the Beat This '{model}' checkpoint: {error}",
                status_code=502,
                details={"model": model, "url": url},
            ) from error
