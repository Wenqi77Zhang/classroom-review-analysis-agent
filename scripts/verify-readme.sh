#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for required in './setup.sh' './start.sh' './verify.sh' 'qwen3.5:4b'; do
  grep -Fq "$required" "$root/README.md" || { echo "README missing: $required" >&2; exit 1; }
done
bash "$root/verify.sh"
echo "README command contract and release verification passed."
