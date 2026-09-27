from pathlib import Path
from typing import Protocol


class BeatDetector(Protocol):
    name: str
    model_name: str
    resolved_device: str

    def detect(self, path: Path) -> tuple[list[float], list[float]]: ...


class BeatThisDetector:
    name = "beat_this"

    def __init__(self, model_name: str = "final0", device: str = "auto") -> None:
        self.model_name = model_name
        self.requested_device = device
        self.resolved_device = device

    def detect(self, path: Path) -> tuple[list[float], list[float]]:
        import torch
        from beat_this.inference import File2Beats

        self.resolved_device = (
            "cuda" if self.requested_device == "auto" and torch.cuda.is_available() else "cpu"
        )
        if self.requested_device != "auto":
            self.resolved_device = self.requested_device
        detector = File2Beats(
            checkpoint_path=self.model_name,
            device=self.resolved_device,
            dbn=False,
        )
        try:
            beats, downbeats = detector(str(path))
            return [float(value) for value in beats], [float(value) for value in downbeats]
        finally:
            del detector
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
