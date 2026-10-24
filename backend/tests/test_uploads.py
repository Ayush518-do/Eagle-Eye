PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 32


def _post(client, name, data):
    return client.post("/api/uploads", files={"file": (name, data)})


def test_accepts_png_jpg_pdf(client, tmp_path):
    for name, data, ctype in [("a.png", PNG, "image/png"), ("b.jpg", JPG, "image/jpeg"),
                              ("c.pdf", PDF, "application/pdf")]:
        r = _post(client, name, data)
        assert r.status_code == 201, r.text
        assert r.json()["content_type"] == ctype
        assert len(r.json()["sha256"]) == 64
    assert len(list((tmp_path / "uploads").iterdir())) == 3


def test_rejects_renamed_executable(client):
    r = _post(client, "photo.jpg", b"MZ\x90\x00" + b"\x00" * 32)
    assert r.status_code == 400
    assert "Unsupported" in r.json()["detail"]


def test_rejects_empty_and_oversize(client):
    assert _post(client, "e.png", b"").status_code == 400
    big = PNG + b"\x00" * (1024 * 1024)  # limit is 1 MB in tests
    r = _post(client, "big.png", big)
    assert r.status_code == 400
    assert "limit" in r.json()["detail"]


def test_path_in_filename_cannot_escape(client, tmp_path):
    for evil in ("../../evil.png", "..\\..\\evil.png"):
        r = _post(client, evil, PNG)
        assert r.status_code == 201
        assert r.json()["original_name"] == "evil.png"
    assert not (tmp_path / "evil.png").exists()
