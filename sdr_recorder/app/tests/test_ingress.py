from pathlib import Path


def test_frontend_has_no_root_relative_assets_or_api_calls():
    static = Path(__file__).parents[1] / "sdr_recorder" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    assert 'src="/static' not in html
    assert 'href="/static' not in html
    assert "fetch('/" not in js
    assert 'new WebSocket("/' not in js
