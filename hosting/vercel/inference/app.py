"""Private ASGI endpoint for the existing AurisCore analysis service."""
from functools import cache
import hmac
from importlib.util import find_spec
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory, gettempdir
from threading import Lock
from typing import Literal

import numpy as np
import lazy_loader
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

# The deployed code and dependency directories are read-only.
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(gettempdir()) / "auriscore-numba"))
os.environ.setdefault("MPLCONFIGDIR", str(Path(gettempdir()) / "auriscore-matplotlib"))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

root = Path(__file__).resolve().parent


def restore_librosa_stubs():
    """Supply librosa's lazy import stubs when the function builder strips them."""
    spec = find_spec("librosa")
    if spec is None or spec.origin is None or Path(spec.origin).with_suffix(".pyi").is_file():
        return None
    stub_dir = TemporaryDirectory(prefix="auriscore-librosa-")
    for source in (root / "librosa-stubs").rglob("*.pyi.txt"):
        dest = Path(stub_dir.name) / source.relative_to(root / "librosa-stubs").with_suffix("")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
    attach = lazy_loader.attach_stub

    def attach_with_librosa_stubs(package_name: str, filename: str):
        package = package_name.split(".")
        if package[0] == "librosa":
            candidate = Path(stub_dir.name).joinpath(*package[1:], "__init__.pyi")
            if candidate.is_file():
                return attach(package_name, str(candidate))
        return attach(package_name, filename)

    lazy_loader.attach_stub = attach_with_librosa_stubs
    return stub_dir


librosa_stubs = restore_librosa_stubs()
sys.path.insert(0, str(root / "scripts"))
from analyze_recording import build_service  # noqa: E402

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
busy = Lock()
pcm_bytes = {"heart": 160000, "lung": 480000, "abdomen": 80000}
max_wav_bytes = 4 * 1024 * 1024


@cache
def service():
    packages = {mode + "_package": Path(value) for mode in pcm_bytes
                if (value := os.environ.get("AURISCORE_" + mode.upper() + "_PACKAGE"))}
    staged_heart = root / "heart-engineering" / "manifest.json"
    if staged_heart.is_file() and "heart_package" not in packages:
        os.environ.setdefault("AURISCORE_ENGINEERING_MODELS", str(staged_heart))
    return build_service(**packages)


def analyze(data: bytearray, mode: str, audio_format: str) -> dict:
    if audio_format == "pcm":
        return service().analyze_pcm(np.frombuffer(data, dtype="<i2"), 8000, mode, encoding="int16")
    return service().analyze_wav(bytes(data), mode)


@app.post("/v1/analysis/{mode}/{audio_format}")
async def analysis(request: Request, mode: Literal["heart", "lung", "abdomen"],
                   audio_format: Literal["pcm", "wav"]) -> JSONResponse:
    secret = os.environ.get("AURISCORE_INFERENCE_TOKEN", "")
    if len(secret) < 16 or not hmac.compare_digest(
        request.headers.get("authorization", "").encode(), ("Bearer " + secret).encode()
    ):
        raise HTTPException(401, "Authentication required")
    expected_type = "application/octet-stream" if audio_format == "pcm" else "audio/wav"
    if request.headers.get("content-type") != expected_type:
        raise HTTPException(415, "Unsupported audio format")
    if not busy.acquire(blocking=False):
        raise HTTPException(429, "Analysis busy")
    try:
        limit = pcm_bytes[mode] if audio_format == "pcm" else max_wav_bytes
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > limit:
                raise HTTPException(413, "Audio too large")
            data.extend(chunk)
        if not data or (audio_format == "pcm" and len(data) != limit):
            raise HTTPException(400, "Incomplete audio")
        try:
            result = await run_in_threadpool(analyze, data, mode, audio_format)
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(503, "Analysis backend unavailable") from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    finally:
        busy.release()
