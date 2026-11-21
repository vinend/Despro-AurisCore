"""Verify authenticated Heart, Lung and Abdomen inference using generated audio."""
import argparse
import hashlib
import io
import json
import math
import os
import random
import struct
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import wave


RATE = 8000
LUNG_MODEL = "EXP-L030-frame-temporal-delta"
ABDOMEN_MODEL = "EXP-A105-abdomen-crnn-specaugment-noise"
HEART_MODEL = "H022-fold1-engineering"
CLASSES = {"wheeze", "rhonchi", "crackle"}
HEART_REFERENCE_SHA256 = "493602122456932b91e62a694bd42f4d2c14f952804d17be85a1613f1ccd4e9f"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = build_opener(NoRedirect())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def fixtures(mode: str) -> tuple[bytes, bytes]:
    rng = random.Random(40)
    seconds, frequency = {"lung": (30, 440), "heart": (10, 55), "abdomen": (5, 130)}[mode]
    pcm = b"".join(struct.pack("<h", round(
        1100 * math.sin(2 * math.pi * frequency * i / RATE) + rng.randint(-500, 500)
    )) for i in range(seconds * RATE))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm)
    return pcm, buffer.getvalue()


def request(base: str, mode: str, kind: str, data: bytes, token: str | None) -> tuple[int, bytes]:
    headers = {"Content-Type": "audio/wav" if kind == "wav" else "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    route = Request(f"{base}/v1/analysis/{mode}/{kind}", data, headers)
    for attempt in range(3):
        try:
            with opener.open(route, timeout=75) as response:
                return response.status, response.read()
        except HTTPError as error:
            if error.code not in {429, 502, 504} or attempt == 2:
                return error.code, error.read()
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("Inference request exhausted retries")


def check_prediction(mode: str, kind: str, status: int, body: bytes) -> dict:
    context = f"{mode}/{kind}"
    require(status == 200, f"{context}: expected HTTP 200, got {status}")
    result = json.loads(body)
    analysis = result.get("analysis") or {}
    require(result.get("schema_version") == "organ-analysis-v1"
            and result.get("mode") == mode and result.get("status") in {"partial", "completed"}
            and result.get("quality", {}).get("valid") is True
            and analysis.get("schema_version") == f"{mode}-analysis-v1",
            f"{context}: analysis unavailable ({[error['code'] for error in result.get('errors', [])]})")
    model = result.get("model_version")
    if mode == "heart":
        murmur = analysis.get("murmur") or {}
        require(model == HEART_MODEL and murmur.get("status") == "available"
                and murmur.get("model_version") == model
                and result.get("usage_scope") == "engineering_test_only",
                f"{context}: expected H022 fold 1 Murmur engineering output")
        score = murmur.get("probability")
        threshold = murmur.get("threshold")
        require(unit_score(score) and unit_score(threshold)
                and murmur.get("label") == ("present" if score >= threshold else "absent"),
                f"{context}: inconsistent Murmur score, threshold or label")
        print(f"{context}: {model}, score={score:.6f}, threshold={threshold:.6f}, label={murmur['label']}")
        return {"score": score, "threshold": threshold}
    if mode == "abdomen":
        detection = analysis.get("event_detection") or {}
        events = analysis.get("bowel_events")
        require(model == ABDOMEN_MODEL and detection.get("model_version") == model
                and detection.get("schema_version") == "abdomen-event-candidates-v1"
                and result.get("usage_scope") == "engineering_test_only"
                and result.get("status") == "partial" and isinstance(events, list),
                f"{context}: expected A105 engineering candidate output")
        onset, offset = detection.get("onset_threshold"), detection.get("offset_threshold")
        duration = detection["analyzed_duration_s"]
        require(unit_score(onset) and unit_score(offset) and offset < onset
                and 0 < duration <= 5
                and all(0 <= event["start_s"] < event["end_s"] <= duration
                        and unit_score(event.get("score")) for event in events),
                f"{context}: invalid event thresholds or candidates")
        print(f"{context}: {model}, candidates={len(events)}, onset={onset}, offset={offset}")
        return {"onset": onset, "offset": offset, "count": len(events),
                **{f"candidate_{i}_{key}": event[key] for i, event in enumerate(events)
                   for key in ("score", "start_s", "end_s")}}
    require(model == LUNG_MODEL and analysis.get("model_version") == model
            and result.get("status") == "partial", f"{context}: expected L030 engineering output")
    require(analysis.get("analyzed_duration_s") == 30
            and analysis.get("respiratory", {}).get("reason") == "model_does_not_support_phases",
            f"{kind}: unexpected duration or respiratory result")
    scores = analysis.get("class_scores", [])
    require(len(scores) == 3 and {item["label"] for item in scores} == CLASSES,
            f"{kind}: expected all three L030 class scores")
    for item in scores:
        for field in ("maximum_frame_score", "threshold"):
            value = item.get(field)
            require(unit_score(value), f"{kind}: invalid {field}")
    require(any(item["maximum_frame_score"] > 0 for item in scores),
            f"{kind}: all scores are zero")
    for event in analysis.get("sound_events", []):
        require(event["label"] in CLASSES and 0 <= event["start_s"] < event["end_s"] <= 30,
                f"{kind}: invalid candidate interval")
    print(f"{context}: {model}, {len(analysis['sound_events'])} candidates, "
          f"scores={json.dumps(scores)}")
    return {item["label"]: item["maximum_frame_score"] for item in scores}


def unit_score(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1


def check_mode(base: str, mode: str, token: str) -> None:
    status, _ = request(base, mode, "pcm", b"", None)
    require(status == 401, f"{mode}: expected anonymous HTTP 401, got {status}")
    pcm, wav = fixtures(mode)
    pcm_values = check_prediction(mode, "pcm", *request(base, mode, "pcm", pcm, token))
    wav_values = check_prediction(mode, "wav", *request(base, mode, "wav", wav, token))
    require(pcm_values.keys() == wav_values.keys()
            and all(math.isclose(value, wav_values[key], abs_tol=1e-4)
                    for key, value in pcm_values.items()),
            f"{mode}: PCM and WAV outputs differ for identical audio")
    status, body = request(base, mode, "pcm", bytes(len(pcm)), token)
    result = json.loads(body) if status == 200 else {}
    require(status == 200 and result.get("status") == "error"
            and result.get("quality", {}).get("reason") == "silent_signal"
            and result.get("quality", {}).get("valid") is False
            and result.get("analysis") is None, f"{mode}: silent PCM must fail the quality gate")
    print(f"{mode}: anonymous request rejected, PCM/WAV agree, silence rejected.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--reference-url", help="Download and verify the published Heart reference WAV")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    url = urlsplit(base)
    require(url.scheme == "https" or (url.scheme == "http" and url.hostname == "127.0.0.1"),
            "Use HTTPS or local loopback for inference credentials")
    token = os.environ.get("AURISCORE_INFERENCE_TOKEN", "")
    require(len(token) >= 16, "AURISCORE_INFERENCE_TOKEN is required")
    failures = []
    for mode in ("lung", "abdomen", "heart"):
        try:
            check_mode(base, mode, token)
        except (SystemExit, OSError, ValueError, KeyError, TypeError) as error:
            failures.append(f"{mode}: {error}")
    require(not failures, "\n".join(failures))
    if args.reference_url:
        require(urlsplit(args.reference_url).scheme == "https", "Use HTTPS for the Heart reference")
        with opener.open(args.reference_url, timeout=20) as response:
            wav = response.read(4 * 1024 * 1024 + 1)
        require(hashlib.sha256(wav).hexdigest() == HEART_REFERENCE_SHA256, "Heart reference checksum mismatch")
        check_prediction("heart", "reference WAV", *request(base, "heart", "wav", wav, token))


if __name__ == "__main__":
    main()
