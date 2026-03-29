import logging

from src.monitor import prepare_urls


def test_prepare_urls_formatting(tmp_path):
    d = tmp_path / "domains.txt"
    d.write_text("google.com\n# comment\nhttps://msu.ru")

    urls = prepare_urls(str(d))

    assert "http://google.com" in urls
    assert "https://google.com" in urls
    assert "https://msu.ru" in urls
    assert len(urls) == 3


def test_prepare_urls_file_not_found(caplog):
    with caplog.at_level(logging.ERROR):
        result = prepare_urls("non_existent_file_123.txt")

    assert result == []
    assert "File not found" in caplog.text
