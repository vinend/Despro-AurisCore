"""Stage the inference service without training scripts, datasets, or local files."""
import argparse
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "AI-Pipeline"
DEST = ROOT / ".runtime" / "vercel-inference"
LUNG = Path("results/EXP-L030-frame-temporal-delta")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEST)
    dest = parser.parse_args().output
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
