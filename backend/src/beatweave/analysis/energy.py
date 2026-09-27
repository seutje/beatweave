from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from beatweave.analysis.schemas import EnergySample


@dataclass(frozen=True)
class EnergySettings:
    sample_rate: int = 22050
    frame_length: int = 2048
    hop_length: int = 512
    rms_weight: float = 0.5
    spectral_flux_weight: float = 0.3
    onset_density_weight: float = 0.2
    lower_percentile: float = 5.0
    upper_percentile: float = 95.0

    @property
    def weights(self) -> dict[str, float]:
        return {
            "rms": self.rms_weight,
            "spectral_flux": self.spectral_flux_weight,
            "onset_density": self.onset_density_weight,
        }


class EnergyAnalyzer:
    def __init__(self, settings: EnergySettings | None = None) -> None:
        self.settings = settings or EnergySettings()

    def analyze(self, samples: NDArray[np.float32]) -> list[EnergySample]:
        config = self.settings
        if samples.size == 0:
            return []
        if samples.size < config.frame_length:
            samples = np.pad(samples, (0, config.frame_length - samples.size))

        frames = np.lib.stride_tricks.sliding_window_view(samples, config.frame_length)[
            :: config.hop_length
        ]
        windowed = frames * np.hanning(config.frame_length)
        rms_raw = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
        spectra = np.abs(np.fft.rfft(windowed, axis=1))
        flux_raw = np.zeros(len(frames), dtype=np.float64)
        if len(frames) > 1:
            flux_raw[1:] = np.maximum(spectra[1:] - spectra[:-1], 0).sum(axis=1)

        threshold = float(np.median(flux_raw) + 1.5 * np.std(flux_raw))
        onsets = (flux_raw > threshold).astype(np.float64)
        density_window = max(1, round(config.sample_rate / config.hop_length))
        density_raw = (
            np.convolve(onsets, np.ones(density_window, dtype=np.float64), mode="same")
            / density_window
        )

        rms = self._normalize(rms_raw)
        flux = self._normalize(flux_raw)
        density = self._normalize(density_raw)
        combined = np.clip(
            config.rms_weight * rms
            + config.spectral_flux_weight * flux
            + config.onset_density_weight * density,
            0,
            1,
        )
        times = (
            np.arange(len(frames), dtype=np.float64) * config.hop_length + config.frame_length / 2
        ) / config.sample_rate
        return [
            EnergySample(
                time=round(float(time), 6),
                value=round(float(value), 6),
                rms=round(float(rms_value), 6),
                spectral_flux=round(float(flux_value), 6),
                onset_density=round(float(density_value), 6),
            )
            for time, value, rms_value, flux_value, density_value in zip(
                times, combined, rms, flux, density, strict=True
            )
        ]

    def _normalize(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        lower, upper = np.percentile(
            values,
            [self.settings.lower_percentile, self.settings.upper_percentile],
        )
        if upper <= lower:
            return np.zeros_like(values)
        return np.clip((values - lower) / (upper - lower), 0, 1)
