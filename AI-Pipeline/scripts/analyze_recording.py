"""One-shot WAV analysis or a persistent JSON-lines recorded-audio worker."""
import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import sys

import _bootstrap  # noqa: F401
from auriscore.analysis_service import AnalysisService, BackendDefinition, HeartDSPBackend


def dispatch(service: AnalysisService, request: object) -> dict:
    """Map a transport request to the shared service without exposing file paths."""
    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object")
    mode, request_id = request.get("mode"), request.get("request_id")
    if "wav_base64" in request:
        if "samples" in request or not isinstance(request["wav_base64"], str):
            raise ValueError("Choose one WAV or PCM input")
        try:
            data = base64.b64decode(request["wav_base64"], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid WAV encoding") from None
        return service.analyze_wav(data, mode, request_id=request_id)
    return service.analyze_pcm(request.get("samples"), request.get("sample_rate"), mode,
                               encoding=request.get("encoding", "float"), request_id=request_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wav", type=Path)
    source.add_argument("--stdin", action="store_true", help="Read WAV bytes from standard input")
    source.add_argument("--serve", action="store_true", help="Read one JSON request and write one response per line")
    parser.add_argument("--mode", choices=["heart", "abdomen"])
    parser.add_argument("--heart-package", type=Path, default=os.environ.get("AURISCORE_HEART_PACKAGE") or None,
                        help="Verified Heart deployment package; audit candidates are rejected")
    parser.add_argument("--abdomen-package", type=Path, default=os.environ.get("AURISCORE_ABDOMEN_PACKAGE") or None,
                        help="Verified bowel-activity deployment package; audit candidates are rejected")
    args = parser.parse_args()
    if (args.wav or args.stdin) and not args.mode:
        parser.error("WAV input requires --mode")
    definitions = [BackendDefinition("heart", "heart-dsp-prototype-0.1.0", HeartDSPBackend)]
    try:
        if args.heart_package:
            from auriscore.heart_inference import heart_backend_definition
            definitions = [heart_backend_definition(args.heart_package)]
        if args.abdomen_package:
            from auriscore.abdomen_inference import abdomen_backend_definition
            definitions.append(abdomen_backend_definition(args.abdomen_package))
        service = AnalysisService(backends=definitions)
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(2, "Deployment package is missing, ineligible or invalid.\n")
    if args.wav or args.stdin:
        try:
            if args.stdin:
                data = sys.stdin.buffer.read(service.policy.max_wav_bytes + 1)
            else:
                with args.wav.open("rb") as stream:
                    data = stream.read(service.policy.max_wav_bytes + 1)
            result = service.analyze_wav(data, args.mode)
        except OSError:
            parser.exit(2, "Recording could not be opened.\n")
        print(json.dumps(result, allow_nan=False))
        raise SystemExit(0 if result["status"] in {"completed", "partial"} else 1)
    max_line = 24 * 1024 * 1024
    while line := sys.stdin.buffer.readline(max_line + 1):
        if len(line) > max_line:
            print(json.dumps(service.invalid_request("Request exceeds the worker limit.")), flush=True)
            raise SystemExit(2)
        try:
            result = dispatch(service, json.loads(line))
        except (ValueError, TypeError, UnicodeDecodeError):
            result = service.invalid_request("Request must contain valid JSON and one supported audio input.")
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
