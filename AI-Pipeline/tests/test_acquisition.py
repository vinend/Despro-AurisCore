"""Network-independent downloader regression tests."""
import io
import hashlib
import pytest
from auriscore.acquisition import download_file, acquire


def test_download_atomic_and_preserves_originals(tmp_path, monkeypatch):
    payload = b"original public bytes"
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    destination = tmp_path / "original.txt"
    download_file("https://example.test/original", destination)
    assert destination.read_bytes() == payload
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch existing originals")))
    download_file("https://example.test/original", destination)
    assert destination.read_bytes() == payload


def test_acquisition_checksum_rejects_changed_original(tmp_path):
    (tmp_path / "original.txt").write_bytes(b"changed bytes")
    digest = hashlib.sha256(b"original bytes").hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(f"{digest} original.txt\n")
    with pytest.raises(ValueError, match="Missing/changed original"):
        acquire(tmp_path)
    assert (tmp_path / "original.txt").read_bytes() == b"changed bytes"
