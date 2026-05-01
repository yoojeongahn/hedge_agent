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
