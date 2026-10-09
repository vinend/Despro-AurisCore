"""CPU-only Heart DSP file-adapter demo; prints one heart-analysis-v1 JSON result."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

import soundfile as sf

import _bootstrap  # noqa: F401
from auriscore.heart_result import analyze_heart
from auriscore.murmur_inference import FreezeIntegrityError, H021MurmurAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Prototype Heart DSP on one local mono WAV")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wav", type=Path, help="Path to one WAV file")
    source.add_argument("--stdin", action="store_true", help="Read WAV bytes from standard input")
    args = parser.parse_args()
    wav_input = BytesIO(sys.stdin.buffer.read()) if args.stdin else args.wav
    audio, sample_rate = sf.read(wav_input, dtype="float64", always_2d=False)
    freeze = Path(__file__).resolve().parents[1] / "analysis" / "HEART-DEVELOPMENT-FREEZE-H021"
    try:
        murmur_service = H021MurmurAdapter(freeze)
    except FreezeIntegrityError:
        # The DSP demo remains available when research metadata is absent/broken.
        murmur_service = None
    print(json.dumps(analyze_heart(audio, sample_rate, murmur_service=murmur_service),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
