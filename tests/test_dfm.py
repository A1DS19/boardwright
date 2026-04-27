"""DFM profile data + .kicad_pro mutation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardwright.tools import pcb_checks, project


MINIMAL_PRO = {
    "board": {
        "design_settings": {
            "rules": {
                "min_track_width": 0.0,
                "min_clearance": 0.0,
                "min_via_diameter": 0.5,
                "min_through_hole_diameter": 0.3,
                "min_via_annular_width": 0.1,
                "min_copper_edge_clearance": 0.5,
                "min_hole_clearance": 0.25,
                "min_hole_to_hole": 0.25,
                "min_silk_clearance": 0.0,
                "solder_mask_to_copper_clearance": 0.0,
                "min_text_height": 0.8,
                "min_text_thickness": 0.08,
            }
        }
    }
}


@pytest.fixture
def project_files(tmp_path):
    """Write a minimal .kicad_pcb + .kicad_pro pair and register them."""
    pcb = tmp_path / "test.kicad_pcb"
    pcb.write_text("(kicad_pcb (version 20240108) (generator pcbnew))")
    pro = tmp_path / "test.kicad_pro"
    pro.write_text(json.dumps(MINIMAL_PRO))
    project.set_project(pcb_file=str(pcb))
    return pcb, pro


# ─────────────────────────────────────────────────────────────────────────────
# Profile data invariants
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_PROFILES = {
    "jlcpcb",
    "jlcpcb_advanced",
    "pcbway",
    "pcbway_advanced",
    "oshpark",
    "oshpark_4layer",
}

REQUIRED_RULE_KEYS = {
    "min_track_width",
    "min_clearance",
    "min_via_diameter",
    "min_through_hole_diameter",
    "min_via_annular_width",
    "min_copper_edge_clearance",
}


def test_expected_profiles_present():
    assert set(pcb_checks.DFM_PROFILES) == EXPECTED_PROFILES


def test_each_profile_has_required_metadata():
    for name, profile in pcb_checks.DFM_PROFILES.items():
        assert "fab" in profile, f"{name}: missing fab"
        assert "tier" in profile, f"{name}: missing tier"
        assert "url" in profile and profile["url"].startswith("http"), f"{name}: bad url"
        assert "rules" in profile, f"{name}: missing rules"


def test_each_profile_covers_required_rules():
    for name, profile in pcb_checks.DFM_PROFILES.items():
        missing = REQUIRED_RULE_KEYS - set(profile["rules"])
        assert not missing, f"{name}: missing rule keys {missing}"


def test_rule_values_are_positive_floats():
    for name, profile in pcb_checks.DFM_PROFILES.items():
        for key, value in profile["rules"].items():
            assert isinstance(value, (int, float)), f"{name}.{key}: not numeric"
            assert value > 0, f"{name}.{key}: must be > 0 (got {value})"


def test_advanced_tiers_are_tighter_than_standard():
    """Advanced tiers must specify *equal or smaller* track widths than standard."""
    pairs = [
        ("jlcpcb", "jlcpcb_advanced"),
        ("pcbway", "pcbway_advanced"),
    ]
    for std_name, adv_name in pairs:
        std = pcb_checks.DFM_PROFILES[std_name]["rules"]["min_track_width"]
        adv = pcb_checks.DFM_PROFILES[adv_name]["rules"]["min_track_width"]
        assert adv < std, f"{adv_name} ({adv}) should be tighter than {std_name} ({std})"


# ─────────────────────────────────────────────────────────────────────────────
# .kicad_pro mutation
# ─────────────────────────────────────────────────────────────────────────────

def test_apply_jlcpcb_writes_rules(project_files):
    _pcb, pro = project_files
    result = pcb_checks.dfm_apply_jlcpcb()
    assert result["status"] == "ok"
    assert result["fab"] == "JLCPCB"

    written = json.loads(pro.read_text())
    rules = written["board"]["design_settings"]["rules"]
    assert rules["min_track_width"] == 0.127
    assert rules["min_clearance"] == 0.127
    assert rules["min_through_hole_diameter"] == 0.3


def test_apply_jlcpcb_advanced_picks_advanced_tier(project_files):
    _pcb, pro = project_files
    result = pcb_checks.dfm_apply_jlcpcb(advanced=True)
    assert result["status"] == "ok"
    assert "advanced" in result["tier"]
    rules = json.loads(pro.read_text())["board"]["design_settings"]["rules"]
    assert rules["min_track_width"] == 0.0889  # 3.5 mil


def test_apply_pcbway_writes_rules(project_files):
    _pcb, pro = project_files
    result = pcb_checks.dfm_apply_pcbway()
    assert result["status"] == "ok"
    assert result["fab"] == "PCBWay"
    rules = json.loads(pro.read_text())["board"]["design_settings"]["rules"]
    assert rules["min_track_width"] == 0.1524  # 6 mil


def test_apply_oshpark_two_layer_default(project_files):
    _pcb, pro = project_files
    result = pcb_checks.dfm_apply_oshpark()
    assert result["status"] == "ok"
    assert "two-layer" in result["tier"]
    rules = json.loads(pro.read_text())["board"]["design_settings"]["rules"]
    assert rules["min_via_annular_width"] == 0.18  # 7 mil ring


def test_apply_oshpark_four_layer(project_files):
    _pcb, pro = project_files
    result = pcb_checks.dfm_apply_oshpark(four_layer=True)
    assert result["status"] == "ok"
    assert "four-layer" in result["tier"]
    rules = json.loads(pro.read_text())["board"]["design_settings"]["rules"]
    assert rules["min_track_width"] == 0.127


def test_diff_reports_changes(project_files):
    _pcb, _pro = project_files
    result = pcb_checks.dfm_apply_jlcpcb()
    diff = result["rules_changed"]
    assert "min_track_width" in diff
    assert diff["min_track_width"]["old"] == 0.0
    assert diff["min_track_width"]["new"] == 0.127


def test_apply_is_idempotent(project_files):
    _pcb, pro = project_files
    pcb_checks.dfm_apply_jlcpcb()
    second = pcb_checks.dfm_apply_jlcpcb()
    assert second["status"] == "ok"
    assert second["rules_changed"] == {}, "second apply should not show changes"


def test_apply_without_set_project():
    # No project_files fixture here — set_project was not called.
    result = pcb_checks.dfm_apply_jlcpcb()
    assert result["status"] == "error"
    assert "set_project" in result["message"]


def test_apply_unknown_profile_via_internal(project_files):
    result = pcb_checks._apply_dfm_profile("not_a_real_fab")
    assert result["status"] == "error"
    assert "available_profiles" in result


def test_apply_when_pro_file_missing(tmp_path):
    pcb = tmp_path / "lonely.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    project.set_project(pcb_file=str(pcb))
    # No .kicad_pro alongside
    result = pcb_checks.dfm_apply_jlcpcb()
    assert result["status"] == "error"
    assert "Project file not found" in result["message"]


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry / router integration
# ─────────────────────────────────────────────────────────────────────────────

def test_dfm_tools_in_project_admin_category():
    from boardwright import router
    project_admin = next(c for c in router.TOOL_CATEGORIES if c["name"] == "project_admin")
    assert "dfm_apply_jlcpcb" in project_admin["tools"]
    assert "dfm_apply_pcbway" in project_admin["tools"]
    assert "dfm_apply_oshpark" in project_admin["tools"]


def test_dfm_tools_have_handlers_and_schemas():
    from boardwright import dispatcher
    for name in ("dfm_apply_jlcpcb", "dfm_apply_pcbway", "dfm_apply_oshpark"):
        assert name in dispatcher.ALL_HANDLERS
        assert name in dispatcher.ALL_SCHEMAS


def test_run_drc_preset_enum_includes_fabs():
    from boardwright import dispatcher
    schema = dispatcher.ALL_SCHEMAS["run_drc"]
    enum = schema["input_schema"]["properties"]["rules_preset"]["enum"]
    assert "jlcpcb" in enum
    assert "pcbway" in enum
    assert "oshpark" in enum
