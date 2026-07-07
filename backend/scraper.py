import os
import re
import time
import uuid
import traceback
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import helium as he


HEADLESS = True
DEFAULT_TIMEOUT = 22
RESULTS_TIMEOUT = 24
SHORT_TIMEOUT = 3


def build_chrome_options():
    options = Options()

    chrome_binary = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
    options.binary_location = chrome_binary
    options.page_load_strategy = "eager"

    unique_id = str(uuid.uuid4())
    user_data_dir = f"/tmp/chrome-user-data-{unique_id}"
    cache_dir = f"/tmp/chrome-cache-{unique_id}"

    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--disk-cache-dir={cache_dir}")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--lang=es-AR")

    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    return options


def start_market_browser(url: str):
    driver = webdriver.Chrome(
        options=build_chrome_options()
    )

    he.set_driver(driver)

    driver.set_window_size(1366, 900)
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(0)

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            }
        )
    except Exception:
        pass

    driver.get(url)
    wait_for_dom_ready(timeout=12)

    return driver


ZONES = {
    "Q": {
        "label": "Cualquier zona",
        "markets": ["la_gallega", "la_reina", "coto", "jumbo", "dar"]
    },
    "C": {
        "label": "Centro",
        "markets": ["la_gallega", "coto", "dar"]
    },
    "S": {
        "label": "Sur",
        "markets": ["la_reina", "dar"]
    },
    "O": {
        "label": "Oeste",
        "markets": ["coto", "dar"]
    },
    "F": {
        "label": "Fisherton",
        "markets": ["la_gallega", "coto"]
    },
    "N": {
        "label": "Norte",
        "markets": ["la_gallega", "coto", "jumbo"]
    }
}


MARKET_NAMES = {
    "la_gallega": "La Gallega",
    "la_reina": "La Reina",
    "coto": "Coto",
    "jumbo": "Jumbo",
    "dar": "Dar"
}


def clean_text(text: str) -> str:
    if not text:
        return ""

    return " ".join(text.replace("\n", " ").split()).strip()


def normalize_price(price_text: str) -> Optional[float]:
    if not price_text:
        return None

    text = clean_text(price_text)

    matches = re.findall(r"\$?\s*[\d\.]+,\d{2}|\$?\s*[\d\.]+", text)

    if not matches:
        return None

    raw_price = matches[0]
    raw_price = raw_price.replace("$", "").strip()
    raw_price = raw_price.replace(".", "")
    raw_price = raw_price.replace(",", ".")

    try:
        return float(raw_price)
    except ValueError:
        return None


def relevance_score(query: str, product_name: str) -> int:
    query = query.lower().strip()
    product_name = product_name.lower().strip()

    if not query or not product_name:
        return 0

    score = 0

    if query in product_name:
        score += 50

    query_words = query.split()

    for word in query_words:
        if word in product_name:
            score += 10

    return score


def normalize_image_url(image_url: str, base_url: str) -> str:
    if not image_url:
        return ""

    image_url = image_url.strip()

    if image_url.startswith("data:image"):
        return ""

    if image_url.startswith("http"):
        return image_url

    if image_url.startswith("//"):
        return "https:" + image_url

    if image_url.startswith("/"):
        domain_match = re.match(r"^(https?://[^/]+)", base_url)

        if domain_match:
            return domain_match.group(1) + image_url

    return image_url


def extract_first_srcset_url(srcset: str) -> str:
    if not srcset:
        return ""

    first_part = srcset.split(",")[0].strip()

    if not first_part:
        return ""

    return first_part.split(" ")[0].strip()


def extract_background_image_url(style: str) -> str:
    if not style:
        return ""

    match = re.search(r'url\(["\']?(.*?)["\']?\)', style)

    if not match:
        return ""

    return match.group(1).strip()


def get_driver():
    return he.get_driver()


def wait_for_dom_ready(timeout: int = 12):
    try:
        driver = get_driver()
        WebDriverWait(driver, timeout).until(
            lambda current_driver: current_driver.execute_script(
                "return document.readyState"
            ) in ["interactive", "complete"]
        )
    except Exception:
        pass


def wait_for_css(selector: str, timeout: int = DEFAULT_TIMEOUT):
    driver = get_driver()

    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


def wait_for_clickable_css(selector: str, timeout: int = DEFAULT_TIMEOUT):
    driver = get_driver()

    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
    )


def wait_for_any_css(selectors: List[str], timeout: int = DEFAULT_TIMEOUT):
    driver = get_driver()

    def find_any(current_driver):
        for selector in selectors:
            elements = current_driver.find_elements(By.CSS_SELECTOR, selector)

            if elements:
                return elements[0]

        return False

    return WebDriverWait(driver, timeout).until(find_any)


def wait_for_result_count(
    selector: str,
    min_count: int = 1,
    timeout: int = RESULTS_TIMEOUT
) -> bool:
    driver = get_driver()

    def has_results(current_driver):
        elements = current_driver.find_elements(By.CSS_SELECTOR, selector)
        visible_elements = [element for element in elements if element.is_displayed()]

        return len(visible_elements) >= min_count

    WebDriverWait(driver, timeout).until(has_results)
    return True


def wait_for_results_or_continue(selector: str, timeout: int = RESULTS_TIMEOUT) -> bool:
    try:
        return wait_for_result_count(selector, min_count=1, timeout=timeout)
    except TimeoutException:
        return False


def get_selector_text(selector: str, index: int) -> str:
    try:
        driver = get_driver()
        elements = driver.find_elements(By.CSS_SELECTOR, selector)

        if index >= len(elements):
            return ""

        return elements[index].text
    except Exception:
        return ""


def write_search_and_submit(search_input, product: str):
    he.click(search_input)

    try:
        search_input.web_element.clear()
    except Exception:
        pass

    he.write(product, into=search_input)
    he.press(he.ENTER)


def get_image_src_from_element(element) -> str:
    image_attributes = [
        "currentSrc",
        "src",
        "data-src",
        "data-original",
        "data-lazy",
        "data-lazy-src",
        "data-srcset",
        "srcset",
    ]

    for attribute in image_attributes:
        try:
            value = element.get_attribute(attribute)

            if not value:
                continue

            if "srcset" in attribute.lower():
                value = extract_first_srcset_url(value)

            if value and not value.startswith("data:image"):
                return value

        except Exception:
            pass

    try:
        style = element.get_attribute("style")
        background_url = extract_background_image_url(style)

        if background_url:
            return background_url
    except Exception:
        pass

    try:
        images = element.find_elements(By.CSS_SELECTOR, "img")

        for image in images:
            image_url = get_image_src_from_element(image)

            if image_url:
                return image_url

    except Exception:
        pass

    return ""


def find_product_image_url(
    index: int,
    base_url: str,
    card_selectors: Optional[List[str]] = None,
    image_selectors: Optional[List[str]] = None
) -> str:
    card_selectors = card_selectors or []
    image_selectors = image_selectors or []

    try:
        driver = get_driver()
    except Exception:
        return ""

    for card_selector in card_selectors:
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, card_selector)

            if index < len(cards):
                image_url = get_image_src_from_element(cards[index])
                image_url = normalize_image_url(image_url, base_url)

                if image_url:
                    return image_url

        except Exception:
            pass

    for image_selector in image_selectors:
        try:
            images = driver.find_elements(By.CSS_SELECTOR, image_selector)

            valid_urls = []

            for image in images:
                image_url = get_image_src_from_element(image)
                image_url = normalize_image_url(image_url, base_url)

                if image_url and "logo" not in image_url.lower():
                    valid_urls.append(image_url)

            if index < len(valid_urls):
                return valid_urls[index]

        except Exception:
            pass

    return ""


def build_result(
    supermarket: str,
    product_query: str,
    product_name: str,
    price_text: str,
    url: str,
    image_url: str = ""
) -> Dict:
    price = normalize_price(price_text)

    return {
        "supermarket": supermarket,
        "searched_product": product_query,
        "product_name": clean_text(product_name),
        "price_text": clean_text(price_text),
        "price": price,
        "url": url,
        "image_url": image_url,
        "relevance": relevance_score(product_query, product_name)
    }


def safe_kill_browser():
    try:
        he.kill_browser()
    except Exception:
        pass


def wait_selector(selector: str, timeout: int = DEFAULT_TIMEOUT):
    wait_for_css(selector, timeout=timeout)
    return he.S(selector)


def close_cookies_banner():
    selectors = [
        ".onetrust-close-btn-handler",
        "#onetrust-accept-btn-handler",
        ".banner-close-button",
        ".ot-close-icon",
    ]

    for selector in selectors:
        try:
            wait_for_clickable_css(selector, timeout=SHORT_TIMEOUT)
            button = he.S(selector)

            if button.exists():
                he.click(button)
                return

        except Exception:
            pass


def scrape_la_gallega(product: str, limit: int = 3) -> List[Dict]:
    supermarket = "La Gallega"
    url = "https://www.lagallega.com.ar/login.asp"
    results = []

    try:
        start_market_browser(url)
        close_cookies_banner()

        search_input = wait_selector("#cpoBuscar")
        write_search_and_submit(search_input, product)

        wait_for_results_or_continue(".desc", timeout=RESULTS_TIMEOUT)

        for index in range(limit):
            product_name = get_selector_text(".desc", index)
            product_price = get_selector_text(".izq", index)

            image_url = find_product_image_url(
                index=index,
                base_url=url,
                card_selectors=[
                    ".cuadProd",
                    ".producto",
                    ".itemProducto",
                    ".prod",
                ],
                image_selectors=[
                    ".cuadProd img",
                    ".producto img",
                    ".itemProducto img",
                    ".prod img",
                    "img",
                ]
            )

            if product_name:
                results.append(
                    build_result(
                        supermarket=supermarket,
                        product_query=product,
                        product_name=product_name,
                        price_text=product_price,
                        url=url,
                        image_url=image_url
                    )
                )

    finally:
        safe_kill_browser()

    return results


def scrape_la_reina(product: str, limit: int = 3) -> List[Dict]:
    supermarket = "La Reina"
    url = "https://www.lareinaonline.com.ar/"
    results = []

    try:
        start_market_browser(url)
        close_cookies_banner()

        search_input = wait_selector("#cpoBuscar")
        write_search_and_submit(search_input, product)

        wait_for_results_or_continue(".desc", timeout=RESULTS_TIMEOUT)

        for index in range(limit):
            product_name = get_selector_text(".desc", index)
            product_price = get_selector_text(".izq", index)

            image_url = find_product_image_url(
                index=index,
                base_url=url,
                card_selectors=[
                    ".cuadProd",
                    ".producto",
                    ".itemProducto",
                    ".prod",
                ],
                image_selectors=[
                    ".cuadProd img",
                    ".producto img",
                    ".itemProducto img",
                    ".prod img",
                    "img",
                ]
            )

            if product_name:
                results.append(
                    build_result(
                        supermarket=supermarket,
                        product_query=product,
                        product_name=product_name,
                        price_text=product_price,
                        url=url,
                        image_url=image_url
                    )
                )

    finally:
        safe_kill_browser()

    return results


def scrape_dar(product: str, limit: int = 3) -> List[Dict]:
    supermarket = "Dar"
    url = "https://darentucasa.com.ar/carrito.asp"
    results = []

    try:
        start_market_browser(url)
        close_cookies_banner()

        search_input = wait_selector("#cpoBuscar")
        write_search_and_submit(search_input, product)

        wait_for_results_or_continue(".desc", timeout=RESULTS_TIMEOUT)

        for index in range(limit):
            product_name = get_selector_text(".desc", index)
            product_price = get_selector_text(".izq", index)

            image_url = find_product_image_url(
                index=index,
                base_url=url,
                card_selectors=[
                    ".cuadProd",
                    ".producto",
                    ".itemProducto",
                    ".prod",
                ],
                image_selectors=[
                    ".cuadProd img",
                    ".producto img",
                    ".itemProducto img",
                    ".prod img",
                    "img",
                ]
            )

            if product_name:
                results.append(
                    build_result(
                        supermarket=supermarket,
                        product_query=product,
                        product_name=product_name,
                        price_text=product_price,
                        url=url,
                        image_url=image_url
                    )
                )

    finally:
        safe_kill_browser()

    return results


def scrape_coto(product: str, limit: int = 3) -> List[Dict]:
    supermarket = "Coto"
    url = "https://www.cotodigital.com.ar/sitios/cdigi/nuevositio"
    results = []

    try:
        start_market_browser(url)
        close_cookies_banner()

        search_input = wait_selector("#cio-autocomplete-0-input")
        write_search_and_submit(search_input, product)

        wait_for_results_or_continue(".nombre-producto", timeout=RESULTS_TIMEOUT)

        try:
            he.scroll_down(400)
            he.scroll_down(400)
        except Exception:
            pass

        for index in range(limit):
            product_name = get_selector_text(".nombre-producto", index)
            product_price = get_selector_text(".card-title", index)

            image_url = find_product_image_url(
                index=index,
                base_url=url,
                card_selectors=[
                    ".card",
                    ".card-product",
                    ".product-card",
                    ".producto",
                    ".product",
                    ".item",
                    "article",
                ],
                image_selectors=[
                    ".product-image"
                ]
            )

            if product_name:
                results.append(
                    build_result(
                        supermarket=supermarket,
                        product_query=product,
                        product_name=product_name,
                        price_text=product_price,
                        url=url,
                        image_url=image_url
                    )
                )

    finally:
        safe_kill_browser()

    return results


def scrape_jumbo(product: str, limit: int = 3) -> List[Dict]:
    supermarket = "Jumbo"
    url = "https://www.jumbo.com.ar/"
    results = []

    try:
        start_market_browser(url)
        close_cookies_banner()

        search_input = wait_selector(".vtex-styleguide-9-x-input")
        write_search_and_submit(search_input, product)

        wait_for_results_or_continue(
            ".vtex-product-summary-2-x-productBrand",
            timeout=RESULTS_TIMEOUT
        )

        try:
            he.scroll_down(400)
            he.scroll_down(400)
        except Exception:
            pass

        for index in range(limit):
            product_name = get_selector_text(
                ".vtex-product-summary-2-x-productBrand",
                index
            )

            product_price = get_selector_text(
                ".productPrice",
                index
            )

            image_url = find_product_image_url(
                index=index,
                base_url=url,
                card_selectors=[
                    ".vtex-product-summary-2-x-container",
                    ".vtex-product-summary-2-x-element",
                    ".vtex-search-result-3-x-galleryItem",
                    "article",
                ],
                image_selectors=[
                    ".vtex-product-summary-2-x-image",
                    ".vtex-product-summary-2-x-imageNormal",
                    ".vtex-product-summary-2-x-imageWrapper img",
                    ".vtex-search-result-3-x-galleryItem img",
                    "article img",
                    "img",
                ]
            )

            if product_name:
                results.append(
                    build_result(
                        supermarket=supermarket,
                        product_query=product,
                        product_name=product_name,
                        price_text=product_price,
                        url=url,
                        image_url=image_url
                    )
                )

    finally:
        safe_kill_browser()

    return results


SCRAPERS = {
    "la_gallega": scrape_la_gallega,
    "la_reina": scrape_la_reina,
    "coto": scrape_coto,
    "jumbo": scrape_jumbo,
    "dar": scrape_dar
}


def search_products(product: str, zone: str, limit_per_market: int = 3) -> Dict:
    markets = ZONES[zone]["markets"]

    all_results = []
    errors = []

    for market_key in markets:
        scraper = SCRAPERS.get(market_key)
        market_name = MARKET_NAMES.get(market_key, market_key)

        if scraper is None:
            errors.append({
                "supermarket": market_name,
                "message": "No hay scraper configurado para este supermercado."
            })
            continue

        try:
            market_results = scraper(product, limit=limit_per_market)
            all_results.extend(market_results)

            if len(market_results) == 0:
                errors.append({
                    "supermarket": market_name,
                    "message": "No se encontraron resultados."
                })

        except Exception as error:
            errors.append({
                "supermarket": market_name,
                "message": str(error),
                "trace": traceback.format_exc()
            })

    return {
        "results": all_results,
        "errors": errors
    }