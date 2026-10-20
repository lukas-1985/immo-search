from pathlib import Path

import pytest

from immo.config import DEFAULT_CONFIG_DIR, ConfigError, load_config


def test_example_config_is_valid():
    config = load_config(DEFAULT_CONFIG_DIR)
    assert "mfh-beispiel" in config.profiles
    assert config.settings.schedule.run.every_hours == 3
    assert config.settings.schedule.run.from_ == "07:00"
    assert "verworfen" in config.settings.workflow.end_status


def test_finance_merge(config):
    profile = config.profiles["mfh-a"]
    assert config.finance_for(profile).zins is None  # keine Defaults in der Test-settings.yaml
    profile.finance.zins = 0.04
    assert config.finance_for(profile).zins == 0.04


def _write_profile(config_dir: Path, text: str) -> None:
    (config_dir / "profiles" / "mfh-a.yaml").write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("id: mfh-a\nname: x\nobjektart: villa\nfredy: {jobs: [a]}", "objektart"),
        ("id: mfh-a\nname: x\nobjektart: mehrfamilienhaus\nfredy: {}", "jobs"),
        ("id: mfh-a\nname: x\nobjektart: mehrfamilienhaus\nfredy: {jobs: [a]}\nfetch_filter: {preis: {min: 5, max: 1}}", "min"),
        ("id: mfh-a\nname: x\nobjektart: mehrfamilienhaus\nfredy: {jobs: [a]}\ntippfehler: 1", "tippfehler"),
        ("id: anders\nname: x\nobjektart: mehrfamilienhaus\nfredy: {jobs: [a]}", "Dateinamen"),
        ("id: mfh-a\nname: x\nobjektart: mehrfamilienhaus\nfredy: {jobs: [a]}\nfinance: {bundesland: XX}", "Bundesland"),
        ("id: mfh-a\nname: [x\n", "YAML"),
    ],
)
def test_invalid_profiles_are_rejected(config_dir, text, expected):
    _write_profile(config_dir, text)
    with pytest.raises(ConfigError, match=expected):
        load_config(config_dir)


def test_unknown_profile(config):
    with pytest.raises(ConfigError, match="nicht gefunden"):
        config.active_profiles("gibt-es-nicht")


def test_afa_satz_auto_aus_alter_settings():
    from immo.config import SteuernSettings

    assert SteuernSettings(afa_satz="auto").afa_satz == 0.02
    assert SteuernSettings().gebaeudeanteil == 0.80
