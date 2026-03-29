import asyncio
import logging
from typing import Dict, List, Optional, Tuple

import aiohttp


async def check_url(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    timeout: int,
) -> Tuple[bool, str]:
    """
    Выполняет асинхронную диагностику доступности ресурса.

    Args:
        session (aiohttp.ClientSession): Общая сессия для запросов.
        url (str): Адрес ресурса.
        semaphore (asyncio.Semaphore): Ограничитель конкурентных запросов.
        timeout (int): Таймаут ожидания ответа.

    Returns:
        Tuple[bool, str]: Пара (статус_доступности, описание_результата).
    """
    async with semaphore:
        try:
            async with session.get(
                url, timeout=timeout, raise_for_status=True
            ) as resp:
                return True, f"OK ({resp.status})"

        except (
            aiohttp.ClientConnectorSSLError,
            aiohttp.ClientConnectorCertificateError,
        ) as ssl_err:
            try:
                async with session.get(
                    url, timeout=timeout, ssl=False
                ) as resp:
                    return False, f"SSL Error, technical UP ({resp.status})"
            except Exception:
                return False, f"SSL Error: {str(ssl_err)}"

        except aiohttp.ClientResponseError as e:
            return False, f"HTTP Error {e.status}"

        except aiohttp.ClientConnectorDNSError:
            return False, "DNS Error: Domain not found"

        except aiohttp.ClientConnectorError as e:
            return False, f"Connection refused: {str(e)}"

        except asyncio.TimeoutError:
            return False, "Timeout"

        except Exception as e:
            return False, f"Unexpected: {type(e).__name__}"


class Monitor:
    """Основной класс сервиса мониторинга на базе независимых воркеров."""

    def __init__(
        self,
        urls: List[str],
        interval: int,
        timeout: int,
        max_req: int,
        fast_interval: int = 2,
        reduced_timeout: int = 2,
    ) -> None:
        """
        Инициализация монитора.

        Args:
            urls: Список целевых URL.
            interval: Стандартный интервал проверки (сек).
            timeout: Стандартный таймаут (сек).
            max_req: Лимит одновременных соединений.
            fast_interval: Интервал для упавших сайтов (сек).
            reduced_timeout: Сокращенный таймаут для упавших сайтов (сек).
        """
        self.urls = urls
        self.interval = interval
        self.timeout = timeout
        self.fast_interval = fast_interval
        self.reduced_timeout = reduced_timeout
        self.semaphore = asyncio.Semaphore(max_req)
        self.states: Dict[str, str] = {}

    async def _worker(self, session: aiohttp.ClientSession, url: str) -> None:
        """
        Независимый цикл мониторинга для конкретного URL.

        Args:
            session: Активная сессия aiohttp.
            url: Целевой адрес.
        """
        last_state: Optional[str] = None

        while True:
            cur_timeout = (
                self.reduced_timeout if last_state == "DOWN" else self.timeout
            )

            is_up, message = await check_url(
                session, url, self.semaphore, cur_timeout
            )
            new_state = "UP" if is_up else "DOWN"

            if last_state is None:
                if new_state == "UP":
                    logging.info(f"STARTUP: {url} is UP | {message}")
                else:
                    logging.warning(f"STARTUP: {url} is DOWN | {message}")

            elif last_state != new_state:
                if new_state == "UP":
                    logging.info(f"RECOVERY: {url} is back ONLINE | {message}")
                else:
                    logging.error(f"FAILURE: {url} is now OFFLINE | {message}")

            self.states[url] = new_state
            last_state = new_state

            sleep_time = self.interval if is_up else self.fast_interval
            await asyncio.sleep(sleep_time)

    async def run(self) -> None:
        """Запуск мониторинга: создание сессии и активация воркеров."""
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
        headers = {"User-Agent": ua}

        async with aiohttp.ClientSession(
            headers=headers, max_line_size=16384, max_field_size=16384
        ) as session:
            logging.info(f"--- Starting monitor for {len(self.urls)} URLs ---")

            tasks = [
                asyncio.create_task(self._worker(session, url))
                for url in self.urls
            ]
            await asyncio.gather(*tasks)
