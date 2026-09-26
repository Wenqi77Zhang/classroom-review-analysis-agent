"""Create narrated MP4 files from validated courseware previews."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def synthesize_speech(text: str, path: Path) -> None:
    escaped_text = text.replace("'", "''")
    escaped_path = str(path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$voice.Rate=-1;"
        f"$voice.SetOutputToWaveFile('{escaped_path}');"
        f"$voice.Speak('{escaped_text}');"
        "$voice.Dispose()"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    run(["pwsh", "-NoProfile", "-EncodedCommand", encoded])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rounds = json.loads((args.build_dir / "narration.json").read_text(encoding="utf-8"))
    generated: list[Path] = []
    for round_data in rounds:
        slug = round_data["slug"]
        work = args.build_dir / slug / "media"
        work.mkdir(parents=True, exist_ok=True)
        segments = []
        for index, narration in enumerate(round_data["narration"], 1):
            image_path = args.build_dir / slug / f"slide-{index}.png"
            audio_path = work / f"slide-{index}.wav"
            segment_path = work / f"segment-{index}.mp4"
            synthesize_speech(narration, audio_path)
            run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-loop", "1", "-framerate", "25", "-i", str(image_path),
                    "-i", str(audio_path), "-af", "apad=pad_dur=0.6",
                    "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(segment_path),
                ]
            )
            segments.append(segment_path)
        concat_file = work / "segments.txt"
        concat_file.write_text(
            "".join(f"file '{segment.name}'\n" for segment in segments),
            encoding="utf-8",
        )
        output_path = args.output_dir / f"{slug}-classroom.mp4"
        run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", str(output_path),
            ]
        )
        generated.extend((output_path, args.output_dir / f"{slug}-courseware.pptx"))
    manifest = {
        "purpose": "Synthetic, privacy-safe public demonstration only",
        "teaching_effect_evidence": False,
        "license": "CC BY 4.0",
        "source_assets": [
            {
                "name": "binary-classification-background.png",
                "bytes": (args.output_dir / "binary-classification-background.png").stat().st_size,
                "sha256": sha256(args.output_dir / "binary-classification-background.png"),
                "provenance": "Generated specifically for this project with OpenAI ImageGen",
            }
        ],
        "files": [
            {"name": item.name, "bytes": item.stat().st_size, "sha256": sha256(item)}
            for item in generated
        ],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for round_data in rounds:
        shutil.rmtree(args.build_dir / round_data["slug"] / "media")


if __name__ == "__main__":
    main()
