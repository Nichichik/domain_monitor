import logging
from typing import List


def prepare_urls(filename: str) -> List[str]:
    """
    Читает файл с доменами и формирует список уникальных URL с протоколами.

    Args:
        filename (str): Путь к текстовому файлу.

    Returns:
        List[str]: Список отформатированных URL.
    """
    urls = set()
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith(("http://", "https://")):
                    urls.add(line)
                else:
                    urls.add(f"http://{line}")
                    urls.add(f"https://{line}")
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
    return list(urls)
