from pathlib import Path


def test_flight_finder_skill_declares_terminal_json_workflow() -> None:
    skill = (Path("skills") / "flight-finder" / "SKILL.md").read_text(encoding="utf-8")

    assert "name: flight-finder" in skill
    assert "requires_toolsets: [terminal]" in skill
    assert "hermes-flights watch check --json" in skill
    assert "Never invent availability" in skill
    assert "Do not use Markdown tables" in skill
    assert "automatically run `booking options`" in skill
    assert "Show booking links immediately in the same response" in skill
    assert "Treat `booking_options_warning`" in skill
    assert "Never ask whether the user wants a link" in skill
    assert "exactly [SILENT]" in skill


def test_flight_finder_skill_includes_cli_reference() -> None:
    reference = (Path("skills") / "flight-finder" / "references" / "cli.md").read_text(
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
