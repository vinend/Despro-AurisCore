"""Stage the inference service without training scripts, datasets, or local files."""
import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, distribution
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "AI-Pipeline"
DEST = ROOT / ".runtime" / "vercel-inference"
LUNG = Path("results/EXP-L030-frame-temporal-delta")
ABDOMEN = Path("results/EXP-A105-abdomen-crnn-specaugment-noise")
HEART_ASSETS = {"model": "acoustic.keras", "normalization": "normalization.json", "head": "head.npz"}


def stage_heart(archive: Path, expected_sha: str, dest: Path) -> None:
    """Copy only manifest-bound Heart files from the published H022 release."""
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_sha.lower():
            raise ValueError("Heart bundle archive SHA-256 mismatch")
    output = dest / "heart-engineering"
    output.mkdir()
    with ZipFile(archive) as bundle:
        if bundle.getinfo("manifest.json").file_size > 65536:
            raise ValueError("Heart bundle manifest too large")
        manifest = json.loads(bundle.read("manifest.json"))
        if manifest.get("scope") != "engineering_test_only" or manifest.get("deployment_eligible") is not False:
            raise ValueError("Expected explicitly scoped Heart engineering assets")
        heart = manifest["models"]["heart"]
        if (set(heart["hashes"]) != set(HEART_ASSETS)
                or heart["version"] != "H022-fold1-engineering"
                or any(heart.get(key) != filename for key, filename in HEART_ASSETS.items())):
            raise ValueError("Incomplete Heart engineering manifest")
        for key, filename in HEART_ASSETS.items():
            member = bundle.getinfo(filename)
            if not 0 < member.file_size <= 64 * 1024 * 1024:
                raise ValueError("Unexpected Heart model asset size")
            data = bundle.read(member)
            if hashlib.sha256(data).hexdigest() != heart["hashes"][key]:
                raise ValueError(f"Heart {key} SHA-256 mismatch")
            (output / filename).write_bytes(data)
        license_name = "CirCor-ODC-By-1.0.txt"
        (output / license_name).write_bytes(bundle.read(license_name))
    (output / "manifest.json").write_text(json.dumps({
        "scope": "engineering_test_only", "deployment_eligible": False,
        "models": {"heart": {**heart, **HEART_ASSETS}},
    }), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST)
    parser.add_argument("--heart-bundle", type=Path)
    parser.add_argument("--heart-bundle-sha256")
    args = parser.parse_args()
    if bool(args.heart_bundle) != bool(args.heart_bundle_sha256):
        parser.error("Supply both Heart bundle arguments or neither.")
    dest = args.output
    requirements = (ROOT / "hosting/requirements.txt").read_text()
    expected_librosa = next(line.split("==", 1)[1] for line in requirements.splitlines()
                            if line.startswith("librosa=="))
    try:
        librosa = distribution("librosa")
    except PackageNotFoundError:
        parser.error(f"Install librosa=={expected_librosa} in the staging Python environment.")
    if librosa.version != expected_librosa:
        parser.error(f"Staging requires librosa=={expected_librosa}.")
    librosa_root = Path(librosa.locate_file("librosa"))
    stubs = sorted(librosa_root.rglob("*.pyi"))
    license_file = next((file for file in (librosa.files or ()) if file.name == "LICENSE.md"), None)
    if not stubs or license_file is None:
        parser.error("The installed librosa package lacks runtime stubs or its license.")
    # A fresh root prevents stale local content from entering a deployment.
    dest.mkdir(parents=True, exist_ok=False)
    for name in ("app.py", "vercel.json"):
        shutil.copyfile(ROOT / "hosting/vercel/inference" / name, dest / name)
    shutil.copytree(PIPELINE / "src/auriscore", dest / "src/auriscore",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dest / "scripts").mkdir()
    for name in ("_bootstrap.py", "analyze_recording.py"):
        shutil.copyfile(PIPELINE / "scripts" / name, dest / "scripts" / name)
    (dest / LUNG).mkdir(parents=True)
    for name in ("config.json", "best_model.keras", "normalization.npz"):
        shutil.copyfile(PIPELINE / LUNG / name, dest / LUNG / name)
    (dest / ABDOMEN).mkdir()
    for name in ("best_model.keras", "tflite_metadata.json"):
        shutil.copyfile(PIPELINE / ABDOMEN / name, dest / ABDOMEN / name)
    if args.heart_bundle:
        stage_heart(args.heart_bundle, args.heart_bundle_sha256, dest)
    # Vercel removes dependency .pyi files, which librosa reads at runtime.
    for stub in stubs:
        target = (dest / "librosa-stubs" / stub.relative_to(librosa_root)).with_suffix(".pyi.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stub, target)
    shutil.copyfile(librosa.locate_file(license_file), dest / "librosa-stubs/LICENSE.md")
    (dest / "requirements.txt").write_text(requirements + "\nfastapi==0.117.1\n")
    (dest / ".python-version").write_text("3.12\n")
    print(dest)


if __name__ == "__main__":
    main()
