"""Research tools: component search, datasheets, footprint verification, impedance."""

from __future__ import annotations

import math


def search_components(
    query: str,
    package: str | None = None,
    max_results: int = 5,
    in_stock_only: bool = True,
    preferred_distributors: list[str] | None = None,
) -> dict:
    """
    Stub: Search Octopart/Mouser for components.

    Replace with real Octopart GraphQL API call:
      https://octopart.com/api/v4/reference
    or Mouser Search API:
      https://www.mouser.com/api-hub/
    """
    return {
        "status": "ok",
        "note": "STUB — wire up a real distributor API",
        "results": [
            {
                "mpn": f"STUB-{query[:8].upper().replace(' ', '-')}",
                "manufacturer": "StubCorp",
                "description": query,
                "package": package or "SOT-23",
                "stock_mouser": 9999,
                "price_usd_qty10": 0.42,
                "kicad_footprint_hint": f"Package_TO_SOT_SMD:{package or 'SOT-23'}",
                "datasheet_url": "https://example.com/stub_datasheet.pdf",
            }
        ],
    }


def get_datasheet(mpn: str, manufacturer: str | None = None) -> dict:
    """Stub: Fetch and parse a component datasheet."""
    return {
        "status": "ok",
        "note": "STUB — wire up a real datasheet fetch/parse pipeline",
        "mpn": mpn,
        "manufacturer": manufacturer or "Unknown",
        "pins": [],
        "recommended_footprint": "Package_TO_SOT_SMD:SOT-23",
        "decoupling_recommendation": "100nF ceramic on each VCC pin",
        "layout_notes": "Keep decoupling caps within 2mm of power pins.",
        "max_ratings": {},
    }


def verify_kicad_footprint(library: str, footprint: str) -> dict:
    """Stub: Check whether a footprint exists in the KiCad standard libraries."""
    full_path = f"{library}:{footprint}"
    known_prefixes = (
        "Resistor_SMD", "Capacitor_SMD", "Package_TO_SOT_SMD",
        "Package_SO", "Package_DFN_QFN", "Connector_USB",
        "Connector_JST", "RF_Module",
    )
    found = any(library.startswith(p) for p in known_prefixes)
    return {
        "status": "ok",
        "found": found,
        "full_path": full_path if found else None,
        "close_matches": [] if found else [
            f"{library}:{footprint}_HandSoldering",
            f"{library}:{footprint.split('_')[0]}",
        ],
        "note": "STUB — replace with real KiCad library lookup",
    }


def generate_custom_footprint(
    reference: str,
    package_type: str,
    pad_count: int,
    pitch_mm: float | None = None,
    body_width_mm: float | None = None,
    body_height_mm: float | None = None,
    pad_width_mm: float | None = None,
    pad_height_mm: float | None = None,
    courtyard_margin_mm: float = 0.5,
) -> dict:
    """Stub: Generate a .kicad_mod file from land-pattern dimensions."""
    fp_name = f"Custom_{reference}_{package_type}_{pad_count}pad"
    return {
        "status": "ok",
        "note": "STUB — replace with real footprint generator",
        "footprint_name": fp_name,
        "library_path": f"[project]:{fp_name}",
        "kicad_mod_written": False,
    }


def impedance_calc(
    target_impedance_ohm: float,
    trace_type: str,
    layer: str = "F.Cu",
    dielectric_thickness_mm: float = 0.2,
    dielectric_constant: float = 4.5,
    copper_thickness_mm: float = 0.035,
) -> dict:
    """
    Impedance calculator using simplified closed-form IPC-2141A formulae.
    Good to ±10% for standard FR4 stackups — use a proper field solver for
    production designs.
    """
    if trace_type == "microstrip":
        H = dielectric_thickness_mm
        T = copper_thickness_mm
        Er = dielectric_constant

        def z0(W):
            return (87.0 / math.sqrt(Er + 1.41)) * math.log(5.98 * H / (0.8 * W + T))

        lo, hi = 0.01, 5.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if z0(mid) > target_impedance_ohm:
                lo = mid
            else:
                hi = mid
        width_mm = round((lo + hi) / 2.0, 4)
        return {
            "status": "ok",
            "trace_type": trace_type,
            "target_impedance_ohm": target_impedance_ohm,
            "calculated_width_mm": width_mm,
            "layer": layer,
            "stackup": {
                "dielectric_thickness_mm": H,
                "dielectric_constant": Er,
                "copper_thickness_mm": T,
            },
            "note": "IPC-2141A microstrip approximation ±10%. Verify with field solver for production.",
        }

    if trace_type == "differential":
        single = impedance_calc(
            target_impedance_ohm * 0.55,
            "microstrip", layer,
            dielectric_thickness_mm, dielectric_constant, copper_thickness_mm,
        )
        w = single["calculated_width_mm"]
        s = round(w * 1.5, 4)
        return {
            "status": "ok",
            "trace_type": "differential",
            "target_differential_impedance_ohm": target_impedance_ohm,
            "calculated_width_mm": w,
            "recommended_spacing_mm": s,
            "note": (
                "Differential pair estimate — each trace width approximated. "
                "Verify with a proper differential pair impedance calculator."
            ),
        }

    return {
        "status": "error",
        "message": (
            f"Impedance calculation for trace_type='{trace_type}' not implemented. "
            "Use a field solver for stripline / coplanar waveguide."
        ),
    }


HANDLERS = {
    "search_components":         search_components,
    "get_datasheet":             get_datasheet,
    "verify_kicad_footprint":    verify_kicad_footprint,
    "generate_custom_footprint": generate_custom_footprint,
    "impedance_calc":            impedance_calc,
}


TOOL_SCHEMAS = [
    {
        "name": "search_components",
        "description": (
            "Search Octopart and Mouser for real, in-stock components matching a "
            "functional description. Returns MPN, manufacturer, package, price, "
            "availability, and KiCad footprint hint. Use to build the BOM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Functional description, e.g. '3.3V LDO 500mA SOT-23-5'"
                },
                "package": {
                    "type": "string",
                    "description": "Preferred package, e.g. 'SOT-23', '0402', 'QFN-16'"
                },
                "max_results": {"type": "integer", "default": 5},
                "in_stock_only": {"type": "boolean", "default": True},
                "preferred_distributors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Mouser", "Digi-Key"]
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_datasheet",
        "description": (
            "Fetch and parse the datasheet for a given MPN. Returns: pin diagram, "
            "application schematic, recommended footprint, absolute max ratings, "
            "and any layout recommendations from the datasheet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mpn": {"type": "string"},
                "manufacturer": {"type": "string"}
            },
            "required": ["mpn"]
        }
    },
    {
        "name": "verify_kicad_footprint",
        "description": (
            "Check if a footprint exists in the installed KiCad standard libraries "
            "or project-local library. Returns the full library path if found, "
            "or a list of close matches if exact match not found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "library": {"type": "string", "description": "e.g. 'Package_SO'"},
                "footprint": {"type": "string", "description": "e.g. 'SOIC-8_3.9x4.9mm_P1.27mm'"}
            },
            "required": ["library", "footprint"]
        }
    },
    {
        "name": "generate_custom_footprint",
        "description": (
            "Generate a KiCad footprint (.kicad_mod) from datasheet land pattern "
            "dimensions. Use when verify_kicad_footprint returns no match."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "package_type": {
                    "type": "string",
                    "enum": ["SMD", "THT", "QFN", "BGA", "DFN", "SOT", "SOIC", "TO", "custom"]
                },
                "pad_count": {"type": "integer"},
                "pitch_mm": {"type": "number"},
                "body_width_mm": {"type": "number"},
                "body_height_mm": {"type": "number"},
                "pad_width_mm": {"type": "number"},
                "pad_height_mm": {"type": "number"},
                "courtyard_margin_mm": {"type": "number", "default": 0.5}
            },
            "required": ["reference", "package_type", "pad_count"]
        }
    },
    {
        "name": "impedance_calc",
        "description": (
            "Calculate trace width for a target impedance given the PCB stackup. "
            "Use for USB (90Ω diff), RF (50Ω single-ended), or any controlled-impedance trace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_impedance_ohm": {"type": "number"},
                "trace_type": {
                    "type": "string",
                    "enum": ["microstrip", "stripline", "coplanar_waveguide", "differential"]
                },
                "layer": {"type": "string", "description": "e.g. 'F.Cu', 'In1.Cu'"},
                "dielectric_thickness_mm": {"type": "number", "default": 0.2},
                "dielectric_constant": {"type": "number", "default": 4.5},
                "copper_thickness_mm": {"type": "number", "default": 0.035}
            },
            "required": ["target_impedance_ohm", "trace_type"]
        }
    },
]
