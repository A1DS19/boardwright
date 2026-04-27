"""Research tools: component search, datasheets, footprint verification, impedance."""

from __future__ import annotations

import difflib
import math
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote

import pdfplumber
import requests
from dotenv import load_dotenv

from ..state import _kicad_lib_search_paths, _project_state

load_dotenv()

_MOUSER_SEARCH_URL = "https://api.mouser.com/api/v1/search/keyword"
_JLCSEARCH_URL = "https://jlcsearch.tscircuit.com/api/search"
_JLCSEARCH_USER_AGENT = "boardwright/0.3.0 (+https://github.com/A1DS19/boardwright)"
_DATASHEET_FOLDER = "mcp_kicad_datasheets"
_REQUEST_TIMEOUT = 10  # seconds for external HTTP requests


def _datasheets_dir() -> Path | None:
    """
    Return (and create) the datasheets folder inside the active project directory.
    Returns None if no project has been set via set_project().
    """
    anchor = _project_state.get("pcb_file") or _project_state.get("sch_file")
    if not anchor:
        return None
    folder = Path(anchor).parent / _DATASHEET_FOLDER
    folder.mkdir(exist_ok=True)
    return folder

# Section header patterns for datasheet parsing
_SECTION_HEADERS = [
    "absolute maximum",
    "maximum ratings",
    "pin description",
    "pin function",
    "pinout",
    "typical application",
    "application circuit",
    "recommended circuit",
    "decoupling",
    "bypass capacitor",
    "electrical characteristics",
    "dc characteristics",
    "register summary",
    "block diagram",
    "package",
]


def _parse_stock(availability: str) -> int:
    """Extract integer stock count from Mouser's availability string (e.g. '1,234 In Stock')."""
    digits = re.sub(r"[^\d]", "", availability.split(" ")[0])
    return int(digits) if digits else 0


def _extract_package(image_path: str) -> str | None:
    """
    Extract package code from Mouser's ImagePath filename.
    e.g. '.../TQFP_32_t.jpg' -> 'TQFP-32'
    """
    if not image_path:
        return None
    filename = image_path.rstrip("/").split("/")[-1]          # TQFP_32_t.jpg
    stem = filename.rsplit(".", 1)[0]                          # TQFP_32_t
    stem = re.sub(r"_t$", "", stem)                           # TQFP_32
    return stem.replace("_", "-") if stem else None


def _price_at_qty(price_breaks: list[dict], target_qty: int = 10) -> float | None:
    """Return the unit price (USD) for the break that covers target_qty, or the last break."""
    if not price_breaks:
        return None
    best = None
    for pb in price_breaks:
        try:
            qty = int(pb.get("Quantity", 0))
            price_str = pb.get("Price", "").replace(",", ".")
            price = float(re.sub(r"[^\d.]", "", price_str))
        except (ValueError, TypeError):
            continue
        if qty <= target_qty:
            best = price
    return best


def search_components(
    query: str,
    package: str | None = None,
    max_results: int = 5,
    in_stock_only: bool = True,
    preferred_distributors: list[str] | None = None,
) -> dict:
    """Search Mouser for real in-stock components matching a keyword query."""
    api_key = os.getenv("MOUSER_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "error",
            "message": "MOUSER_API_KEY not set — add it to your .env file.",
        }

    # Append package to query if provided so Mouser filters by package type
    keyword = f"{query} {package}".strip() if package else query
    search_options = "InStock" if in_stock_only else "None"

    payload = {
        "SearchByKeywordRequest": {
            "keyword": keyword,
            "Records": max_results,
            "StartingRecord": 0,
            "SearchOptions": search_options,
        }
    }

    try:
        resp = requests.post(
            _MOUSER_SEARCH_URL,
            params={"apiKey": api_key},
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"status": "error", "message": f"Mouser API request failed: {exc}"}

    data = resp.json()
    errors = data.get("Errors") or []
    if errors:
        return {"status": "error", "message": "; ".join(str(e) for e in errors)}

    parts = (
        data.get("SearchResults", {}).get("Parts") or []
    )

    results = []
    for p in parts:
        results.append({
            "mpn": p.get("ManufacturerPartNumber") or p.get("MouserPartNumber", ""),
            "mouser_mpn": p.get("MouserPartNumber", ""),
            "manufacturer": p.get("Manufacturer", ""),
            "description": p.get("Description", ""),
            "package": _extract_package(p.get("ImagePath", "")),
            "stock_mouser": _parse_stock(p.get("Availability", "0")),
            "price_usd_qty10": _price_at_qty(p.get("PriceBreaks", [])),
            "lead_time": p.get("LeadTime") or None,
            "lifecycle_status": p.get("LifecycleStatus") or None,
            "suggested_replacement": p.get("SuggestedReplacement") or None,
            "product_url": p.get("ProductDetailUrl") or None,
            "datasheet_url": p.get("DataSheetUrl") or p.get("ProductDetailUrl") or None,
            "kicad_footprint_hint": None,  # Mouser does not provide KiCad footprints
        })

    return {"status": "ok", "results": results}


def search_components_lcsc(
    query: str,
    package: str | None = None,
    max_results: int = 20,
    basic_only: bool = True,
) -> dict:
    """Search LCSC / JLCPCB for parts via the tscircuit.com public proxy.

    Indie-maker workflow: "is this part on JLCPCB and is it a Basic part
    (cheap assembly) or Extended (loading fee)?" `basic_only=True` filters
    to JLCPCB Basic parts — the cheapest assembly tier.

    Returns LCSC part numbers ready for use in BOMs and pick-and-place files
    submitted to JLCPCB Assembly. Zero-auth — no API key needed.
    """
    params: dict[str, str] = {"q": query, "limit": str(max_results)}
    if package:
        params["package"] = package
    if basic_only:
        params["is_basic"] = "true"

    try:
        resp = requests.get(
            _JLCSEARCH_URL,
            params=params,
            headers={"User-Agent": _JLCSEARCH_USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"status": "error", "message": f"JLCSearch request failed: {exc}"}

    try:
        data = resp.json()
    except ValueError as exc:
        return {"status": "error", "message": f"JLCSearch returned non-JSON: {exc}"}

    components = data.get("components") or []

    results = []
    for c in components:
        lcsc = c.get("lcsc") or ""
        results.append({
            "lcsc": str(lcsc) if lcsc else None,
            "mpn": c.get("mfr") or None,
            "package": c.get("package") or None,
            "description": c.get("description") or "",
            "stock_jlcpcb": c.get("stock"),
            "price_usd": c.get("price"),
            "is_basic": bool(c.get("is_basic")),
            "is_preferred": bool(c.get("is_preferred")),
            "datasheet_url": c.get("datasheet") or None,
            "product_url": (
                f"https://www.lcsc.com/product-detail/{lcsc}.html" if lcsc else None
            ),
        })

    return {
        "status": "ok",
        "source": "jlcsearch.tscircuit.com",
        "query": query,
        "package": package,
        "basic_only": basic_only,
        "result_count": len(results),
        "results": results,
        "note": (
            "Basic parts are pre-loaded on JLCPCB assembly machines (no setup fee). "
            "Extended parts cost ~$3 per unique component to load. Prefer Basic when available."
        ),
    }


def _find_datasheet_url(mpn: str) -> tuple[str | None, str | None]:
    """
    Search Mouser for the MPN and return (datasheet_url, product_url).
    Falls back to scraping the product page if the API returns no direct PDF link.
    """
    api_key = os.getenv("MOUSER_API_KEY", "").strip()
    if not api_key:
        return None, None

    try:
        resp = requests.post(
            _MOUSER_SEARCH_URL,
            params={"apiKey": api_key},
            json={"SearchByKeywordRequest": {
                "keyword": mpn,
                "Records": 1,
                "StartingRecord": 0,
                "SearchOptions": "None",
            }},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        parts = resp.json().get("SearchResults", {}).get("Parts") or []
    except requests.RequestException:
        return None, None

    if not parts:
        return None, None

    p = parts[0]
    ds_url = p.get("DataSheetUrl") or ""
    product_url = p.get("ProductDetailUrl") or ""

    if ds_url:
        return ds_url, product_url

    # Fallback: DuckDuckGo HTML search for a direct PDF datasheet
    pdf_url = _duckduckgo_datasheet(mpn)
    return pdf_url, product_url


def _duckduckgo_datasheet(mpn: str) -> str | None:
    """
    Search DuckDuckGo for '{mpn} datasheet filetype:pdf' and return the first
    direct PDF URL found. DuckDuckGo encodes result URLs as uddg= query params.
    """
    query = f"{mpn} datasheet filetype:pdf"
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    # DuckDuckGo wraps result URLs: uddg=https%3A%2F%2F...
    encoded = re.findall(r"uddg=(https?%3A%2F%2F[^&\"'\s]+)", resp.text)
    for enc in encoded:
        url = unquote(enc)
        if url.lower().endswith(".pdf"):
            return url

    # Also try bare PDF URLs that might appear directly
    bare = re.findall(r"https?://[^\s\"'<>&]+\.pdf", resp.text)
    if bare:
        return bare[0]

    return None


def _extract_sections(pdf_path: str) -> dict[str, str]:
    """
    Extract named text sections from the first 12 pages of a datasheet PDF.
    Returns a dict of lowercased header keyword → block of text following it.
    """
    sections: dict[str, str] = {}
    full_lines: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:12]:
            text = page.extract_text() or ""
            full_lines.extend(text.splitlines())

    # Walk lines, detect section starts, collect text blocks
    current_key: str | None = None
    buffer: list[str] = []

    for line in full_lines:
        lower = line.lower().strip()
        matched = next((h for h in _SECTION_HEADERS if h in lower), None)
        if matched and len(lower) < 120:          # avoid matching mid-sentence
            if current_key and buffer:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = matched
            buffer = [line]
        elif current_key:
            buffer.append(line)

    if current_key and buffer:
        sections[current_key] = "\n".join(buffer).strip()

    return sections


def _parse_max_ratings(text: str) -> dict[str, str]:
    """Best-effort extraction of parameter → value pairs from a max ratings block."""
    ratings: dict[str, str] = {}
    # Match lines like:  VCC  Supply Voltage  ..... 6.0 V
    for line in text.splitlines():
        # Look for a value+unit at the end of the line
        m = re.search(r"([\-\d\.]+\s*(?:V|mA|A|MHz|°C|W|mW))", line)
        if m:
            label = re.sub(r"\s{2,}", " ", line[:m.start()]).strip(" .")
            if label:
                ratings[label] = m.group(1).strip()
    return ratings


def _parse_pins(text: str) -> list[dict]:
    """Best-effort extraction of pin number + name + function rows."""
    pins: list[dict] = []
    for line in text.splitlines():
        # Match patterns like: "1  VCC  Power supply"  or  "PC0 (ADC0)  I/O"
        m = re.match(r"^\s*(\d{1,3})\s+([A-Z][A-Z0-9_/\(\)]{1,20})\s+(.*)", line)
        if m:
            pins.append({
                "number": m.group(1),
                "name": m.group(2).strip(),
                "function": m.group(3).strip(),
            })
    return pins


def get_datasheet(mpn: str, manufacturer: str | None = None) -> dict:
    """Fetch and parse a component datasheet PDF via Mouser, returning structured data."""
    ds_dir = _datasheets_dir()
    if ds_dir is None:
        return {
            "status": "error",
            "message": "No project set. Call set_project(sch_file=...) first so datasheets are saved inside your project folder.",
        }
    safe_name = re.sub(r"[^\w\-]", "_", mpn) + ".pdf"
    pdf_path = ds_dir / safe_name
    cached = pdf_path.exists()

    ds_url, product_url = None, None

    if not cached:
        ds_url, product_url = _find_datasheet_url(mpn)
        if not ds_url:
            return {
                "status": "error",
                "mpn": mpn,
                "manufacturer": manufacturer,
                "product_url": product_url,
                "message": (
                    "No datasheet PDF found via Mouser. "
                    "Check product_url manually if set."
                ),
            }

        # Download and save
        try:
            pdf_resp = requests.get(ds_url, timeout=_REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            pdf_resp.raise_for_status()
        except requests.RequestException as exc:
            return {"status": "error", "mpn": mpn, "message": f"Failed to download datasheet: {exc}"}

        content_type = pdf_resp.headers.get("Content-Type", "")
        content = pdf_resp.content
        if not content[:4] == b"%PDF" and "pdf" not in content_type.lower():
            return {"status": "error", "mpn": mpn, "message": "URL did not return a valid PDF"}
        pdf_path.write_bytes(content)

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)

    sections = _extract_sections(str(pdf_path))

    max_ratings = _parse_max_ratings(
        sections.get("absolute maximum") or sections.get("maximum ratings") or ""
    )
    pins = _parse_pins(
        sections.get("pin description") or sections.get("pin function") or sections.get("pinout") or ""
    )

    # Extract recommended footprint from package section or max-ratings text
    footprint_hint = None
    pkg_text = sections.get("package") or ""
    for pkg in ("TQFP-32", "DIP-28", "QFN-32", "SOIC-28", "PDIP-28"):
        if pkg.lower() in (sections.get("absolute maximum", "") + pkg_text).lower():
            footprint_hint = pkg
            break

    decoupling = ""
    for key in ("decoupling", "bypass capacitor"):
        if key in sections:
            # Grab the first meaningful sentence
            first = next((l for l in sections[key].splitlines() if len(l) > 20), "")
            decoupling = first
            break

    layout_notes = ""
    for key in ("typical application", "recommended circuit", "application circuit"):
        if key in sections:
            first = next((l for l in sections[key].splitlines() if len(l) > 20), "")
            layout_notes = first
            break

    return {
        "status": "ok",
        "mpn": mpn,
        "manufacturer": manufacturer,
        "datasheet_url": ds_url,
        "product_url": product_url,
        "saved_path": str(pdf_path),
        "cached": cached,
        "page_count": page_count,
        "pins": pins,
        "max_ratings": max_ratings,
        "recommended_footprint": footprint_hint,
        "decoupling_recommendation": decoupling or None,
        "layout_notes": layout_notes or None,
        "raw_sections": {k: v[:800] for k, v in sections.items()},  # truncated for readability
    }


def _kicad_fp_search_paths(project_dir: "Path | None" = None) -> list[Path]:
    """Return candidate directories to search for KiCad footprint libraries (.pretty)."""
    return _kicad_lib_search_paths("footprints", "KICAD_FOOTPRINTS", project_dir)


_FP_DOWNLOAD_HINT = (
    "Please download the KiCad footprint (.kicad_mod) from one of: "
    "https://www.snapeda.com, https://componentsearchengine.com, or https://www.ultralibrarian.com. "
    "Save the file into the project's 'footprints/' folder, then tell me: "
    "(1) the filename you saved it as (without .kicad_mod) — this is the footprint name; "
    "(2) the footprint name inside the file if it differs (visible after '(footprint \"' "
    "at the top of the file)."
)


def verify_kicad_footprint(library: str, footprint: str) -> dict:
    """Check whether a footprint exists in the KiCad libraries or project footprints/."""
    full_path = f"{library}:{footprint}"

    pcb_file = _project_state.get("pcb_file")
    sch_file = _project_state.get("sch_file")
    project_dir = Path(pcb_file).parent if pcb_file else (
        Path(sch_file).parent if sch_file else None
    )

    for search_dir in _kicad_fp_search_paths(project_dir):
        # Footprint libraries are .pretty directories containing .kicad_mod files
        lib_dir = search_dir / f"{library}.pretty"
        if lib_dir.is_dir():
            mod_file = lib_dir / f"{footprint}.kicad_mod"
            if mod_file.is_file():
                return {"status": "ok", "found": True, "full_path": full_path}
        # Also allow a flat footprints/ folder with bare .kicad_mod files
        mod_file = search_dir / f"{footprint}.kicad_mod"
        if mod_file.is_file():
            return {"status": "ok", "found": True, "full_path": full_path}

    return {
        "status": "ok",
        "found": False,
        "full_path": None,
        "message": (
            f"Footprint '{full_path}' not found in any KiCad library or project "
            f"footprints/ folder. {_FP_DOWNLOAD_HINT}"
        ),
    }
    def expand(u: str) -> str:
        for k, v in env.items():
            u = u.replace("${" + k + "}", v)
        return u
    return {nick: expand(uri) for nick, uri in pairs}


def verify_kicad_footprint(library: str, footprint: str) -> dict:
    """Check whether a footprint exists on disk in a resolvable KiCad library."""
    tables = _find_fp_lib_tables()
    if not tables:
        return {"status": "error",
                "message": "No fp-lib-table found (checked project dir and ~/.config/kicad/*)."}

    libs: dict[str, str] = {}
    for t in tables:
        for k, v in _parse_fp_lib_table(t).items():
            libs.setdefault(k, v)

    if library not in libs:
        close = difflib.get_close_matches(library, list(libs.keys()), n=5, cutoff=0.5)
        return {"status": "ok", "found": False,
                "reason": f"Library '{library}' not in fp-lib-table.",
                "close_library_matches": close}

    lib_dir = Path(libs[library])
    if not lib_dir.exists():
        return {"status": "ok", "found": False,
                "reason": f"Library dir does not exist: {lib_dir}"}

    mod_file = lib_dir / f"{footprint}.kicad_mod"
    if mod_file.exists():
        return {"status": "ok", "found": True,
                "full_path": f"{library}:{footprint}",
                "file": str(mod_file)}

    available = [p.stem for p in lib_dir.glob("*.kicad_mod")]
    close = difflib.get_close_matches(footprint, available, n=8, cutoff=0.5)
    return {"status": "ok", "found": False,
            "reason": f"No '{footprint}.kicad_mod' in {lib_dir}.",
            "close_footprint_matches": [f"{library}:{m}" for m in close]}


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
    """Generate a .kicad_mod file from land-pattern dimensions (not yet implemented)."""
    return {
        "status": "error",
        "message": (
            "Custom footprint generation is not yet implemented. "
            "Please download a footprint from https://www.snapeda.com, "
            "https://componentsearchengine.com, or https://www.ultralibrarian.com "
            "and place it in the project's 'footprints/' folder."
        ),
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
    "search_components_lcsc":    search_components_lcsc,
    "get_datasheet":             get_datasheet,
    "verify_kicad_footprint":    verify_kicad_footprint,
    "generate_custom_footprint": generate_custom_footprint,
    "impedance_calc":            impedance_calc,
}


TOOL_SCHEMAS = [
    {
        "name": "search_components",
        "description": (
            "Search Mouser for real, in-stock components matching a functional "
            "description. Returns MPN, manufacturer, package, price, availability, "
            "and product URL. Requires MOUSER_API_KEY in .env. For JLCPCB-bound "
            "designs, prefer search_components_lcsc — it returns LCSC part numbers "
            "and Basic/Extended flags directly."
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
        "name": "search_components_lcsc",
        "description": (
            "Search LCSC / JLCPCB for parts via the public jlcsearch.tscircuit.com "
            "proxy (zero-auth, no API key needed). Returns LCSC part number, MPN, "
            "package, JLCPCB stock, price, and the Basic/Extended flag — the single "
            "most important field for indie makers using JLCPCB Assembly. "
            "Basic parts are pre-loaded on JLC's assembly machines (no setup fee); "
            "Extended parts cost ~$3 each to load. Use this whenever the user is "
            "building a board they intend to fab and assemble at JLCPCB."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Functional description or MPN, e.g. '3.3V LDO 500mA SOT-23' or 'AMS1117-3.3'"
                },
                "package": {
                    "type": "string",
                    "description": "Optional package filter, e.g. 'SOT-23', '0402', 'QFN-32'"
                },
                "max_results": {
                    "type": "integer",
                    "default": 20,
                    "description": "Up to 20 typically; JLC search is fast"
                },
                "basic_only": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true (default), only return JLCPCB Basic parts (cheapest assembly). "
                        "Set false to include Extended parts (~$3/unique-component setup fee)."
                    )
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
