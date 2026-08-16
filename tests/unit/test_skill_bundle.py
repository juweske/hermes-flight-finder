from pathlib import Path


def test_flight_tracker_skill_declares_terminal_json_workflow() -> None:
    skill = (Path("skills") / "flight-tracker" / "SKILL.md").read_text(encoding="utf-8")

    assert "name: flight-tracker" in skill
    assert "requires_toolsets: [terminal]" in skill
    assert "hermes-flights watch check --json" in skill
    assert "Never invent availability" in skill
    assert "exactly [SILENT]" in skill


def test_flight_tracker_skill_includes_cli_reference() -> None:
    reference = (Path("skills") / "flight-tracker" / "references" / "cli.md").read_text(
        encoding="utf-8"
    )

    assert "hermes-flights search" in reference
    assert "hermes-flights dates" in reference
    assert "hermes-flights watch add" in reference


def test_cron_documentation_keeps_silent_checks_explicit() -> None:
    documentation = (Path("docs") / "hermes-cron.md").read_text(encoding="utf-8")

    assert "hermes-flights watch check --json" in documentation
    assert "exactly `[SILENT]`" in documentation
    assert "hermes cron create" in documentation
