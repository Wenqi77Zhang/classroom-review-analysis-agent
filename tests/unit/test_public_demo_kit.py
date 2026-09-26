from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "examples" / "public-demo"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_public_demo_manifest_matches_distributed_files() -> None:
    manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["purpose"] == "Synthetic, privacy-safe public demonstration only"
    assert manifest["teaching_effect_evidence"] is False
    assert manifest["license"] == "CC BY 4.0"
    assert manifest["source_assets"] == [
        {
            "name": "binary-classification-background.png",
            "bytes": (DEMO_DIR / "binary-classification-background.png").stat().st_size,
            "sha256": file_sha256(DEMO_DIR / "binary-classification-background.png"),
            "provenance": "Generated specifically for this project with OpenAI ImageGen",
        }
    ]
    assert {entry["name"] for entry in manifest["files"]} == {
        "round-1-classroom.mp4",
        "round-1-courseware.pptx",
        "round-2-classroom.mp4",
        "round-2-courseware.pptx",
    }
    for entry in manifest["files"]:
        artifact = DEMO_DIR / entry["name"]
        assert artifact.stat().st_size == entry["bytes"]
        assert file_sha256(artifact) == entry["sha256"]


def test_public_demo_media_and_courseware_have_expected_structure() -> None:
    for round_number in (1, 2):
        video = DEMO_DIR / f"round-{round_number}-classroom.mp4"
        assert b"ftyp" in video.read_bytes()[:32]

        courseware = DEMO_DIR / f"round-{round_number}-courseware.pptx"
        with zipfile.ZipFile(courseware) as archive:
            slides = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            assert len(slides) == 3


def test_public_demo_license_preserves_evidence_boundary() -> None:
    license_text = (DEMO_DIR / "LICENSE.md").read_text(encoding="utf-8")

    assert "CC BY 4.0" in license_text
    assert "no student data" in license_text
    assert "not recordings of real teaching" in license_text
    assert "must not be cited" in license_text


def test_secret_checks_only_allow_the_manifested_demo_videos() -> None:
    shell_check = (ROOT / "scripts/check-secrets.sh").read_text(encoding="utf-8")
    powershell_check = (ROOT / "scripts/check-secrets.ps1").read_text(encoding="utf-8")
    exact_allowlist = r"^examples/public-demo/round-[12]-classroom\.mp4$"

    assert exact_allowlist in shell_check
    assert exact_allowlist in powershell_check
    assert "public-demo/.*" not in shell_check
    assert "public-demo/.*" not in powershell_check
