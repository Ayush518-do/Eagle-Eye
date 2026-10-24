def test_health_both_paths(client):
    for path in ("/health", "/api/health"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_model_status_reports_missing_detector(client):
    r = client.get("/api/model/status")
    assert r.status_code == 200
    det = next(m for m in r.json() if m["component"] == "detector")
    assert det["available"] is False
    assert "DETECTOR_WEIGHTS_PATH" in det["detail"]


def test_ml_interface_refuses_instead_of_inventing():
    import pytest
    from ml.interfaces import ModelUnavailableError, detect_components
    with pytest.raises(ModelUnavailableError):
        detect_components("any.jpg")
