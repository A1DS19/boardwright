"""LCSC / JLCPCB component search tests.

These mock requests.get so the tests run hermetically — no live HTTP.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from boardwright.tools import research


JLC_SAMPLE = {
    "components": [
        {
            "lcsc": "C6186",
            "mfr": "AMS1117-3.3",
            "package": "SOT-223",
            "stock": 12500,
            "price": 0.0612,
            "is_basic": True,
            "is_preferred": True,
            "description": "1A 3.3V LDO Linear Regulator",
            "datasheet": "https://datasheet.lcsc.com/lcsc/AMS1117-3.3.pdf",
        },
        {
            "lcsc": "C6187",
            "mfr": "AMS1117-5.0",
            "package": "SOT-223",
            "stock": 800,
            "price": 0.075,
            "is_basic": False,
            "is_preferred": False,
            "description": "1A 5V LDO Linear Regulator",
            "datasheet": None,
        },
    ]
}


def _mock_response(json_payload, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = json_payload
    mock.raise_for_status = MagicMock()
    if status >= 400:
        from requests import HTTPError
        mock.raise_for_status.side_effect = HTTPError(f"{status}")
    return mock


def test_search_returns_normalized_records():
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response(JLC_SAMPLE)) as mock_get:
        out = research.search_components_lcsc(query="3.3V LDO")
    assert out["status"] == "ok"
    assert out["source"] == "jlcsearch.tscircuit.com"
    assert out["result_count"] == 2

    first = out["results"][0]
    assert first["lcsc"] == "C6186"
    assert first["mpn"] == "AMS1117-3.3"
    assert first["package"] == "SOT-223"
    assert first["stock_jlcpcb"] == 12500
    assert first["price_usd"] == pytest.approx(0.0612)
    assert first["is_basic"] is True
    assert first["is_preferred"] is True
    assert first["product_url"] == "https://www.lcsc.com/product-detail/C6186.html"

    # Verify the call shape
    args, kwargs = mock_get.call_args
    assert args[0] == research._JLCSEARCH_URL
    assert kwargs["params"]["q"] == "3.3V LDO"
    assert kwargs["params"]["is_basic"] == "true"  # default basic_only=True
    assert "boardwright" in kwargs["headers"]["User-Agent"]


def test_search_passes_package_filter():
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response(JLC_SAMPLE)) as mock_get:
        research.search_components_lcsc(query="LDO", package="SOT-23-5")
    params = mock_get.call_args.kwargs["params"]
    assert params["package"] == "SOT-23-5"


def test_search_basic_only_false_omits_filter():
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response(JLC_SAMPLE)) as mock_get:
        research.search_components_lcsc(query="LDO", basic_only=False)
    params = mock_get.call_args.kwargs["params"]
    assert "is_basic" not in params


def test_search_handles_http_error():
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response({}, status=503)):
        out = research.search_components_lcsc(query="anything")
    assert out["status"] == "error"
    assert "request failed" in out["message"].lower()


def test_search_handles_network_error():
    from requests import ConnectionError
    with patch("boardwright.tools.research.requests.get", side_effect=ConnectionError("dns")):
        out = research.search_components_lcsc(query="anything")
    assert out["status"] == "error"


def test_search_handles_non_json_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status = MagicMock()
    mock.json.side_effect = ValueError("not json")
    with patch("boardwright.tools.research.requests.get", return_value=mock):
        out = research.search_components_lcsc(query="anything")
    assert out["status"] == "error"
    assert "non-JSON" in out["message"]


def test_search_returns_empty_results_gracefully():
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response({"components": []})):
        out = research.search_components_lcsc(query="totally fake part")
    assert out["status"] == "ok"
    assert out["result_count"] == 0
    assert out["results"] == []


def test_search_handles_missing_components_key():
    """If JLC's API ever changes and omits the 'components' key, we should still return ok with empty results."""
    with patch("boardwright.tools.research.requests.get", return_value=_mock_response({})):
        out = research.search_components_lcsc(query="x")
    assert out["status"] == "ok"
    assert out["result_count"] == 0


def test_lcsc_tool_in_direct_set_and_registered():
    from boardwright import dispatcher, router
    assert "search_components_lcsc" in router.DIRECT_TOOL_NAMES
    assert "search_components_lcsc" in dispatcher.ALL_HANDLERS
    assert "search_components_lcsc" in dispatcher.ALL_SCHEMAS


def test_lcsc_schema_describes_basic_only():
    from boardwright import dispatcher
    schema = dispatcher.ALL_SCHEMAS["search_components_lcsc"]
    props = schema["input_schema"]["properties"]
    assert "basic_only" in props
    assert props["basic_only"]["default"] is True
