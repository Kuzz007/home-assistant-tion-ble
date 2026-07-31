"""Tests for repository metadata and translations."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_manifest() -> None:
    manifest = json.loads(
        (ROOT / "custom_components" / "tion_ble" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["domain"] == "tion_ble"
    assert manifest["config_flow"] is True
    assert manifest["version"] == "0.1.0"
    assert manifest["bluetooth"][0]["service_uuid"].startswith("98f00001")


def test_translations_are_valid_json() -> None:
    translations = ROOT / "custom_components" / "tion_ble" / "translations"
    for language in ("en", "ru"):
        content = json.loads(
            (translations / f"{language}.json").read_text(encoding="utf-8")
        )
        assert content["title"] == "Tion BLE"
        assert content["entity"]["fan"]["breezer"]["name"]
