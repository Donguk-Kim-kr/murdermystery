import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static import mount_frontend


@pytest.fixture
def site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>앱</html>", encoding="utf-8")
    (tmp_path / "assets" / "main.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_frontend(app, str(tmp_path))
    return TestClient(app)


def test_serves_index_and_assets(site):
    assert "앱" in site.get("/").text
    assert site.get("/assets/main.js").text == "console.log(1)"


def test_unknown_page_paths_fall_back_to_index_so_reload_works(site):
    for path in ("/works/3", "/rooms/new/7", "/room"):
        res = site.get(path)
        assert res.status_code == 200 and "앱" in res.text, path


def test_api_routes_still_win_and_unknown_api_paths_stay_json_404(site):
    assert site.get("/api/ping").json() == {"ok": True}
    res = site.get("/api/없는경로")
    assert res.status_code == 404 and "앱" not in res.text


def test_missing_index_is_a_clear_error(tmp_path):
    with pytest.raises(RuntimeError):
        mount_frontend(FastAPI(), str(tmp_path))
