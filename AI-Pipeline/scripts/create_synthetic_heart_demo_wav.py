"""Create an unlabeled synthetic timing demo WAV; never a clinical test signal."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a synthetic Heart DSP demo WAV")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite existing file: {args.output}")
    sample_rate = 8000
    time = np.arange(sample_rate * 8, dtype=np.float64) / sample_rate
    audio = np.zeros_like(time)
    for s1 in np.arange(.4, 7.2, .8):
        for center, amplitude in ((s1, 1.0), (s1 + .3, .7)):
            audio += amplitude * np.sin(2 * np.pi * 65 * (time - center)) * np.exp(
                -.5 * ((time - center) / .016) ** 2)
    sf.write(args.output, audio, sample_rate, format="WAV")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
