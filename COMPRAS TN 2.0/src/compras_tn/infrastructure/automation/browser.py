import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


def create_corporate_browser(folder: Path, headless: bool, page_load_timeout: int = 25, *, network_diagnostics: bool = False, naf_navigation: bool = False, naf_cache_dir: Path | None = None) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    # NAF observes CAS and its Angular controls itself. A GET timeout can abort
    # Angular bundles while an optional external stylesheet is still pending.
    options.page_load_strategy = "none" if naf_navigation else "eager"
    if naf_navigation and naf_cache_dir is not None:
        naf_cache_dir = naf_cache_dir.resolve()
        naf_cache_dir.mkdir(parents=True, exist_ok=True)
        # Persist only Chromium's HTTP cache, never its profile/cookies/login.
        options.add_argument(f"--disk-cache-dir={naf_cache_dir}")
    if network_diagnostics:
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(folder.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        },
    )
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")
    binary = os.environ.get("COMPRAS_TN_CHROME")
    executable = os.environ.get("COMPRAS_TN_CHROMEDRIVER")
    if binary:
        if not Path(binary).is_file():
            raise FileNotFoundError("Falta el navegador incluido. Extraiga el paquete completo y ejecute instalar.py para reparar.")
        options.binary_location = binary
    if executable:
        if not Path(executable).is_file():
            raise FileNotFoundError("Falta el controlador incluido. Extraiga el paquete completo y ejecute instalar.py para reparar.")
        driver = webdriver.Chrome(options=options, service=Service(executable))
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(
        page_load_timeout
    )
    driver.set_script_timeout(30)
    if naf_navigation:
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:
            driver.quit()
            raise
    return driver
