"""Existing WebApp WAV adapter; prints one compatible heart-analysis-v1 result."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
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
    parser.add_argument("--heart-package", type=Path,
                        default=os.environ.get("AURISCORE_HEART_PACKAGE") or None,
                        help="Verified final Heart package (also AURISCORE_HEART_PACKAGE)")
    args = parser.parse_args()
    backend = None
    if args.heart_package:
        from auriscore.heart_inference import HeartInferenceBackend
        try:
            backend = HeartInferenceBackend(args.heart_package)
        except (ValueError, OSError, KeyError, TypeError):
            parser.exit(3, "Heart deployment package is invalid or unavailable.\n")
    wav_input = BytesIO(sys.stdin.buffer.read()) if args.stdin else args.wav
    audio, sample_rate = sf.read(wav_input, dtype="float64", always_2d=False)
    if backend is not None:
        # Keep the existing API contract: rhythm + events + murmur in one Heart result.
        output = backend.analyze(audio, sample_rate)
        print(json.dumps(output.analysis, indent=2, allow_nan=False))
        return
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
