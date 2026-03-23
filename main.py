import asyncio
import aiohttp
import logging
import os
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))
TIMEOUT = int(os.getenv("TIMEOUT", 10))
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 50))

def prepare_urls(filename: str) -> List[str]:
    urls = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                domain = line.strip()
                if not domain:
                    continue
                if domain.startswith(('http://', 'https://')):
                    urls.append(domain)
                else:
                    urls.append(f"http://{domain}")
                    urls.append(f"https://{domain}")
    except FileNotFoundError:
        logging.error(f"File {filename} not found")

    return urls

async def check_url(session: aiohttp.ClientSession, url:str,
                    semaphore: asyncio.Semaphore) -> Tuple[bool, str]:

    async with semaphore:
        try:
            async with session.get(url, timeout=TIMEOUT, raise_for_status=True) as response:
                return True, f"OK ({response.status})"

        except aiohttp.ClientConnectorSSLError as ssl_err:
            try:
                async with session.get(url, timeout=TIMEOUT, ssl=False) as response:
                    return False, f"SSL Error, but site is UP (Status: {response.status})"

            except Exception:
                return False, f"SSL Error: {response.status}"

        except aiohttp.ClientResponseError as e:
            return False, f"HTTP Error {e.status}: {e.message}"

        except aiohttp.ClientConnectorError as e:
            return False, f"Connection Error {e.status}: {e.message}"

        except asyncio.TimeoutError:
            return False, f"Timeout Error"

        except Exception as e:
            return False, f"Unexpected error: {type(e).__name__}: {str(e)}"


class Monitor:
    def __init__(self, urls: List[str]):
        self.urls = urls
        self.states: Dict[str, str] = {}
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def run(self):
        logging.info(f"Starting monitor for {len(self.urls)} URLs...")

        headers = {'User-Agent':
                       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        async with aiohttp.ClientSession(headers=headers,
                                         max_line_size=16384,
                                         max_field_size=16384
                                         ) as session:
            while True:
                tasks = [check_url(session, url, self.semaphore) for url in self.urls]
                results = await asyncio.gather(*tasks)
                for url, (is_up, message) in zip(self.urls, results):
                    new_state = "UP" if is_up else "DOWN"
                    old_state = self.states.get(url)

                    if old_state != new_state:
                        if new_state == "DOWN":
                            logging.error(f"CHANGE: {url} is DOWN. Reason: {message}")
                        else:
                            logging.info(f"CHANGE: {url} is UP. Reason: {message}")

                        self.states[url] = new_state

                logging.info(f"Cycle finished. Sleeping for {CHECK_INTERVAL} seconds...")
                await asyncio.sleep(CHECK_INTERVAL)

async def main():
    urls = prepare_urls("domains.txt")
    if not urls:
        logging.error("No URLs to check. Exiting.")
        return

    monitor = Monitor(urls)
    try:
        await monitor.run()
    except asyncio.CancelledError:
        logging.info("Monitoring task cancelled.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Service stopped by user (Ctrl+C).")