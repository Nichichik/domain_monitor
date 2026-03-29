import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from .core import Monitor
from .utils import prepare_urls


def parse_args() -> argparse.Namespace:
    """
    Парсит аргументы командной строки.

    Returns:
        Объект с аргументами командной строки.
    """
    parser = argparse.ArgumentParser(
        description="Async Domain Monitor Service"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="domains.txt",
        help="Path to the domains file (default: domains.txt)",
    )
    return parser.parse_args()


async def main() -> None:
    """
    Основная асинхронная точка входа.
    """
    args = parse_args()

    if not os.path.exists(args.file):
        logging.error(f"Input file not found: {args.file}")
        return

    urls = prepare_urls(args.file)
    if not urls:
        logging.error("Domain list is empty.")
        return

    monitor = Monitor(
        urls=urls,
        interval=int(os.getenv("CHECK_INTERVAL", 60)),
        timeout=int(os.getenv("TIMEOUT", 5)),
        max_req=int(os.getenv("MAX_CONCURRENT_REQUESTS", 50)),
    )

    try:
        await monitor.run()
    except asyncio.CancelledError:
        pass


def run_service() -> None:
    """
    Инициализирует окружение и запускает сервис.
    """
    load_dotenv()

    log_path = os.getenv("LOG_FILE_PATH", "logs/monitor.log")
    log_dir = os.path.dirname(log_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Service stopped by user.")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_service()
