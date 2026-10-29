"""Exercise the shared browser and real PDF downloads without corporate data."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from compras_tn.infrastructure.automation.browser import create_corporate_browser


def test_naf_cache_respects_no_store_between_browser_profiles(tmp_path):
    script_requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/main.js":
                script_requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Cache-Control", "no-store")
                # Model NAF's large bundle rather than an in-memory tiny script.
                body = f"window.nafVersion = {len(script_requests)};/*".encode() + b"x" * (1024 * 1024) + b"*/"
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                body = b'<script src="/main.js"></script>'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for version in (1, 2):
            driver = create_corporate_browser(tmp_path, True, network_diagnostics=True,
                naf_navigation=True, naf_cache_dir=tmp_path / "http-cache")
            try:
                driver.get(f"http://127.0.0.1:{server.server_port}/")
                WebDriverWait(driver, 10).until(lambda d: d.execute_script("return window.nafVersion") == version)
                WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState === 'complete'"))
            finally:
                driver.quit()
        assert len(script_requests) == 2, "Se reutilizo un recurso marcado no-store"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("headless", [True, False], ids=["oculto", "visible"])
@pytest.mark.parametrize("naf_navigation", [False, True], ids=["normal", "naf"])
def test_shared_browser_downloads_pdf_in_both_modes(tmp_path, headless, naf_navigation):
    content = b"%PDF-1.4\n% Local download regression\n%%EOF\n"
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/order.pdf":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="OC-prueba.pdf"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b'<a id="download" href="/order.pdf">Descargar OC</a>')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    driver = None
    try:
        driver = create_corporate_browser(tmp_path, headless, network_diagnostics=True, naf_navigation=naf_navigation)
        driver.get(f"http://127.0.0.1:{server.server_port}/")
        WebDriverWait(driver, 10).until(lambda d: d.find_element(By.ID, "download")).click()
        deadline = time.monotonic() + 20
        downloaded = tmp_path / "OC-prueba.pdf"
        while time.monotonic() < deadline and not downloaded.is_file():
            time.sleep(0.1)
        assert downloaded.is_file(), "El navegador no descargó el PDF"
        assert downloaded.read_bytes() == content
        assert not list(tmp_path.glob("*.crdownload"))
        assert driver.execute_script("return navigator.userAgent.includes('HeadlessChrome')") == headless
        from compras_tn.infrastructure.automation.downloads import OrderPortalPage
        diagnostic = OrderPortalPage(driver, tmp_path)._network_diagnostic()
        assert "HTTP 200" in diagnostic
    finally:
        if driver:
            driver.quit()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
