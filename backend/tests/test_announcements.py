"""Kiosk announcements: image/video upload, serving, and the video Range path.

No prior test file existed for this router; these cover the two media kinds
plus the byte-range support that real browsers (Safari/iOS in particular)
require before they'll even attempt to play a <video>.
"""


def test_create_with_image_still_works(client, seeded):
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Görsel Duyuru"},
        files={"media": ("photo.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_image"] is True
    assert body["has_video"] is False
    assert body["image_url"]
    assert body["video_url"] is None

    img = client.get(body["image_url"])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"


def test_create_with_video_serves_full_and_ranged(client, seeded):
    video_bytes = b"0123456789" * 100  # 1000 bytes, enough to slice a range from
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Video Duyuru"},
        files={"media": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["has_video"] is True
    assert body["has_image"] is False
    assert body["video_url"]

    full = client.get(body["video_url"])
    assert full.status_code == 200
    assert full.content == video_bytes
    assert full.headers["accept-ranges"] == "bytes"

    ranged = client.get(body["video_url"], headers={"Range": "bytes=10-19"})
    assert ranged.status_code == 206
    assert ranged.content == video_bytes[10:20]
    assert ranged.headers["content-range"] == f"bytes 10-19/{len(video_bytes)}"

    # Open-ended range ("bytes=N-") goes to the end of the file.
    open_ended = client.get(body["video_url"], headers={"Range": "bytes=990-"})
    assert open_ended.status_code == 206
    assert open_ended.content == video_bytes[990:]


def test_video_over_cap_rejected(client, seeded):
    from app.routers.announcements import MAX_VIDEO_BYTES

    oversized = b"x" * (MAX_VIDEO_BYTES + 1)
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Çok Büyük Video"},
        files={"media": ("big.mp4", oversized, "video/mp4")},
    )
    assert r.status_code == 400
    assert "video" in r.json()["detail"].lower()


def test_non_media_upload_rejected(client, seeded):
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Yanlış Dosya"},
        files={"media": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert r.status_code == 400


def test_missing_video_returns_404(client, seeded):
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Sadece Metin", "body": "İçerik"},
    )
    assert r.status_code == 201
    ann_id = r.json()["id"]
    assert client.get(f"/api/announcements/{ann_id}/video").status_code == 404


def test_kiosk_feed_includes_video_url(client, seeded):
    video_bytes = b"abc" * 50
    r = client.post(
        "/api/announcements",
        headers=seeded["hq_headers"],
        data={"title": "Tüm Kampüs Video"},
        files={"media": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert r.status_code == 201, r.text

    feed = client.get(
        f"/api/kiosk/announcements?campus_id={seeded['campus_a']['id']}"
    ).json()
    assert len(feed["announcements"]) == 1
    assert feed["announcements"][0]["video_url"]
    assert feed["announcements"][0]["image_url"] is None
