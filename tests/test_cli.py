import json
import shutil
from pathlib import Path

import yaml
from click.testing import CliRunner

from cyberpnl.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_statement_end_to_end_is_clearly_a_template(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "statement",
            "--out",
            str(tmp_path),
            "--years",
            "4000",
            "--no-sensitivity",
            "--fail-on-appetite",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Expected annual loss" in result.output and "TEMPLATE" in result.output
    data = json.loads((tmp_path / "statement.json").read_text(encoding="utf-8"))
    assert data["template"] and not data["assumptions_attested"]
    assert data["project"]["creator"] == "Jessen Kurien"
    assert data["appetite"]["within"] and len(data["appetite"]["checks"]) == 2
    assert "benefit_cost_ratio" in data["investments"][0]
    assert (tmp_path / "statement.html").stat().st_size > 10_000
    html_report = (tmp_path / "statement.html").read_text(encoding="utf-8")
    assert '<meta name="viewport"' in html_report
    assert "@media (max-width:900px)" in html_report
    assert html_report.count('class="table-wrap" role="region"') == 2
    assert html_report.count('role="img" aria-label=') >= 4
    assert "not an accounting" in (tmp_path / "statement.md").read_text(encoding="utf-8")


def test_statement_uses_the_model_currency(tmp_path):
    shutil.copytree(ROOT / "model", tmp_path / "model")
    business = tmp_path / "model" / "business.yaml"
    business.write_text(
        business.read_text(encoding="utf-8").replace("currency: USD", "currency: EUR"), encoding="utf-8"
    )
    result = CliRunner().invoke(
        main,
        [
            "statement",
            "--model",
            str(tmp_path / "model"),
            "--out",
            str(tmp_path / "out"),
            "--years",
            "1000",
            "--no-sensitivity",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "€" in result.output
    assert "€" in (tmp_path / "out" / "statement.html").read_text(encoding="utf-8")
    assert "€" in (tmp_path / "out" / "statement.md").read_text(encoding="utf-8")


def test_template_fails_attestation_and_operational_gates(tmp_path):
    common = ["statement", "--out", str(tmp_path), "--years", "2000", "--no-sensitivity"]
    assert CliRunner().invoke(main, [*common, "--require-attested"]).exit_code == 3
    assert CliRunner().invoke(main, [*common, "--require-operational"]).exit_code == 4
    assert CliRunner().invoke(main, ["validate"]).exit_code == 0
    assert CliRunner().invoke(main, ["validate", "--operational"]).exit_code == 4


def test_verify_attest_roundtrip_and_edit_detection(tmp_path):
    shutil.copytree(ROOT / "model", tmp_path / "model")
    model_dir = tmp_path / "model"
    assert CliRunner().invoke(main, ["verify", "--model", str(model_dir)]).exit_code == 1

    lines = []
    for role in ("CFO", "CISO"):
        output = (
            CliRunner()
            .invoke(
                main,
                ["attest", "--model", str(model_dir), "--role", role, "--name", f"{role} Reviewer"],
            )
            .output.strip()
        )
        lines.append(json.loads(output.removeprefix("- ").strip()))
    (model_dir / "register.yaml").write_text(
        yaml.safe_dump({"required_roles": ["CFO", "CISO"], "attestations": lines}, sort_keys=False),
        encoding="utf-8",
    )
    assert CliRunner().invoke(main, ["verify", "--model", str(model_dir)]).exit_code == 0

    imported = CliRunner().invoke(
        main,
        ["kpis", "import", "--model", str(model_dir), "--set", "proven_restore_hours=30"],
    )
    assert imported.exit_code == 0, imported.output
    assert CliRunner().invoke(main, ["verify", "--model", str(model_dir)]).exit_code == 1


def test_kpis_import_from_72md_and_wormprint(tmp_path):
    shutil.copytree(ROOT / "model", tmp_path / "model")
    out72 = tmp_path / "out72"
    out72.mkdir()
    (out72 / "a.json").write_text(
        json.dumps({"expected": "contain", "time_to_contain_minutes": 19.0}), encoding="utf-8"
    )
    (out72 / "b.json").write_text(
        json.dumps({"expected": "contain", "time_to_contain_minutes": 41.0}), encoding="utf-8"
    )
    (out72 / "c.json").write_text(
        json.dumps({"expected": "no_action", "time_to_contain_minutes": None}), encoding="utf-8"
    )
    wormprint = tmp_path / "wormprint.json"
    wormprint.write_text(json.dumps({"exposure_score": 12.5}), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        [
            "kpis",
            "import",
            "--model",
            str(tmp_path / "model"),
            "--from-72md",
            str(out72),
            "--from-wormprint",
            str(wormprint),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "time_to_contain_minutes = 41.0 (measured" in result.output
    assert "credential_exposure_score = 12.5 (measured" in result.output


def test_invalid_kpi_imports_fail_loudly(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(main, ["kpis", "import", "--from-72md", str(empty)])
    assert result.exit_code != 0 and "no valid 72md" in str(result.exception)
    wormprint = tmp_path / "wormprint.json"
    wormprint.write_text(json.dumps({"exposure_score": 120}), encoding="utf-8")
    result = CliRunner().invoke(main, ["kpis", "import", "--from-wormprint", str(wormprint)])
    assert result.exit_code != 0 and "between 0 and 100" in str(result.exception)

    result = CliRunner().invoke(main, ["kpis", "import", "--set", "missing-separator"])
    assert result.exit_code != 0 and "expected KEY=VALUE" in result.output
    result = CliRunner().invoke(main, ["kpis", "import", "--set", "metric=nan"])
    assert result.exit_code != 0 and "must be finite" in result.output

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (5 * 1024 * 1024 + 1))
    result = CliRunner().invoke(main, ["kpis", "import", "--from-wormprint", str(oversized)])
    assert result.exit_code != 0 and "exceeds the 5 MB limit" in str(result.exception)


def test_cli_rejects_unsafe_simulation_parameters():
    result = CliRunner().invoke(main, ["statement", "--years", "0"])
    assert result.exit_code != 0 and "not in the range" in result.output
    result = CliRunner().invoke(main, ["invest", "--seed", "-1"])
    assert result.exit_code != 0 and "not in the range" in result.output


def test_explain_invest_and_register():
    result = CliRunner().invoke(main, ["explain", "ransomware-platform", "--years", "2000"])
    assert result.exit_code == 0 and "contain_before_exfil" in result.output and "unpriced" in result.output
    assert CliRunner().invoke(main, ["explain", "nope"]).exit_code == 1
    result = CliRunner().invoke(main, ["invest", "--years", "2000"])
    assert result.exit_code == 0 and "x" in result.output
    result = CliRunner().invoke(main, ["register"])
    assert result.exit_code == 0 and "0 without source" in result.output
    assert "attestations: NOT CURRENT" in result.output


def test_calibrate_wizard_scripted():
    result = CliRunner().invoke(
        main,
        ["calibrate", "downtime hours", "--unit", "hours"],
        input="10\n100\nr\nw\ni\n40\nIT Director\nworkshop\n",
    )
    assert result.exit_code == 0, result.output
    assert "YAML:" in result.output and "owner: 'IT Director'" in result.output


def test_invalid_model_reports_cleanly(tmp_path):
    shutil.copytree(ROOT / "model", tmp_path / "model")
    path = tmp_path / "model" / "appetite.yaml"
    path.write_text("metric: p95\nmax_pct_revenue: 0.05\nmax_dollars: 1\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["validate", "--model", str(tmp_path / "model")])
    assert result.exit_code == 1 and "model invalid" in result.output
