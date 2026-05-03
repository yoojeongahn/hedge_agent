import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.notifier import split_message


def test_short_message_not_split():
    parts = split_message("hello", limit=4096)
    assert parts == ["hello"]


def test_long_message_splits_on_newline():
    lines = ["line"] * 200
    msg = "\n".join(lines)
    parts = split_message(msg, limit=500)
    assert len(parts) > 1
    for p in parts:
        assert len(p) <= 500


def test_each_part_fits_limit():
    msg = "a" * 5000
    parts = split_message(msg, limit=4096)
    for p in parts:
        assert len(p) <= 4096


def test_send_photo_missing_token(tmp_path):
    fake_img = tmp_path / "chart.png"
    fake_img.write_bytes(b"PNG")
    with patch.dict(os.environ, {}, clear=True):
        from core.notifier import send_photo
        result = send_photo(fake_img)
    assert result is False


def test_send_photo_calls_telegram_api(tmp_path):
    fake_img = tmp_path / "chart.png"
    fake_img.write_bytes(b"PNG")
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}):
        with patch("core.notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp
            from core.notifier import send_photo
            result = send_photo(fake_img)
    assert result is True
    assert mock_post.called
    call_args = mock_post.call_args
    assert "sendPhoto" in call_args[0][0]
