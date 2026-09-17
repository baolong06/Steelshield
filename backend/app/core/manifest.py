from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

BENCHMARK_ROOT = Path(__file__).resolve().parents[3] / "dataset"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def load_manifest() -> dict:
    path = BENCHMARK_ROOT / "manifest.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    hashes = data.get("hashes", {})
    if not hashes.get("all_600_sha256"):
        raise RuntimeError("manifest.yaml missing hashes.all_600_sha256")
    return data


def dataset_integrity() -> dict[str, str]:
    manifest = load_manifest()
    expected = manifest.get("hashes", {})
    checked: dict[str, str] = {}
    mapping = {
        "all_600_sha256": BENCHMARK_ROOT / "cases" / "all_600.jsonl",
        "synthetic_records_sha256": BENCHMARK_ROOT / "fixtures" / "synthetic_records.json",
        "train_sha256": BENCHMARK_ROOT / "splits" / "train.jsonl",
        "calibration_sha256": BENCHMARK_ROOT / "splits" / "calibration.jsonl",
        "evaluation_candidate_sha256": BENCHMARK_ROOT / "splits" / "evaluation_candidate.jsonl",
    }
    for key, path in mapping.items():
        if not path.exists():
            checked[key] = "missing"
            continue
        actual = sha256_file(path)
        checked[key] = "ok" if expected.get(key) == actual else f"mismatch:{actual[:12]}"
    return checked
