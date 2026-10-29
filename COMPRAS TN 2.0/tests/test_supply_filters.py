import base64
from urllib.parse import quote

import pytest
from selenium import webdriver

from compras_tn.infrastructure.automation.downloads import OrderPortalPage
from compras_tn.infrastructure.automation.browser import create_corporate_browser


def pdf_bytes(number):
    stream = (f"BT /F1 12 Tf 50 750 Td (ORDEN DE COMPRA) Tj "
              f"0 -20 Td (BIENES) Tj 0 -20 Td (No {number}) Tj ET").encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return data + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


@pytest.mark.parametrize("headless", [True, False])
@pytest.mark.parametrize("requester", ["1221 - HERRERA PUENTE WILLIAM DANIEL", ""])
def test_supply_filters_in_chrome(tmp_path, headless, requester):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_experimental_option("prefs", {
        "download.default_directory": str(tmp_path),
        "download.prompt_for_download": False,
    })
    driver = create_corporate_browser(tmp_path, headless)
    try:
        html = '''
        <mat-form-field><mat-label>N° Orden</mat-label><input id="order" value="123456"></mat-form-field>
        <div><label>Proveedor</label><ng-select><input aria-autocomplete="list" id="supplier"></ng-select></div>
        <input placeholder="Fecha Desde (dd/MM/YYYY)" id="start">
        <input placeholder="Fecha Hasta (dd/MM/YYYY)" id="end">
        <div><label>Solicitante</label><ng-select><input aria-autocomplete="list" id="requester"></ng-select></div>
        <div><label>Autoriza</label><ng-select><input aria-autocomplete="list" id="authorizer"></ng-select></div>
        <div id="options"></div>
        <button onclick="apply()">Aplicar filtros</button>
        <table><thead><tr><th>No Orden</th></tr></thead><tbody id="results"></tbody></table>
        <script>
        for (const id of ['supplier','requester','authorizer']) {
          document.getElementById(id).oninput = function() {
            const input = this;
            const option = document.createElement('div');
            option.className = 'ng-option'; option.textContent = id === 'requester' ? '1221 - HERRERA PUENTE WILLAM DANIEL' : '2234 - LOPEZ FLORES CARLOS MICHAEL';
            option.onclick = () => { input.value = ''; const label = document.createElement('span'); label.className = 'ng-value-label'; label.textContent = option.textContent; input.closest('ng-select').querySelector('.ng-value-label')?.remove(); input.closest('ng-select').querySelector('.ng-clear-wrapper')?.remove(); input.closest('ng-select').append(label); const clear = document.createElement('span'); clear.className = 'ng-clear-wrapper'; clear.textContent = '×'; clear.onclick = () => {label.remove(); clear.remove(); input.value = '';}; input.closest('ng-select').append(clear); document.getElementById('options').replaceChildren(); };
            document.getElementById('options').replaceChildren(option);
          };
        }
        for (const id of ['start', 'end']) {
          document.getElementById(id).onblur = function() {
            const [month, day, year] = this.value.split('/');
            this.value = [day, month, year].join('/');
          };
        }
        function apply() {
          window.applied = ['order','supplier','start','end','requester','authorizer'].map(id => (document.getElementById(id).closest('ng-select')?.querySelector('.ng-value-label')?.textContent || document.getElementById(id).value));
          if (window.emptyQuery) { document.getElementById('results').innerHTML = '<tr><td colspan=3>No se han encontrado datos</td></tr>'; return; }
          document.getElementById('results').innerHTML = '<tr><td></td><td>' + (document.getElementById('order').value || '123456') + '</td><td><button aria-label="Descargar" onclick="download()">PDF</button></td></tr>';
        }
        function download() {
          const a = document.createElement('a');
          const encoded = document.getElementById('order').value === '654321' ? 'NORMAL_PDF' : 'SUPPLY_PDF';
          a.href = URL.createObjectURL(new Blob([Uint8Array.from(atob(encoded), c => c.charCodeAt(0))], {type:'application/pdf'}));
          a.download = 'orden.pdf'; a.click();
        }
        </script>
        '''
        html = html.replace("NORMAL_PDF", base64.b64encode(pdf_bytes("654321")).decode())
        html = html.replace("SUPPLY_PDF", base64.b64encode(pdf_bytes("123456")).decode())
        driver.get("data:text/html;charset=utf-8," + quote(html))
        page = OrderPortalPage(driver, tmp_path, element_timeout=5, query_timeout=5, download_timeout=10)
        page.configure_supply_filters("01/10/2026", "12/10/2026", requester, "2234 - LOPEZ FLORES CARLOS MICHAEL")
        assert driver.execute_script("return window.applied") == [
            "", "", "01/10/2026", "12/10/2026",
            "1221 - HERRERA PUENTE WILLAM DANIEL" if requester else "", "2234 - LOPEZ FLORES CARLOS MICHAEL",
        ]
        results = page.download_all_visible_results()
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].path.read_bytes().startswith(b"%PDF-")
        normal_pdf = page.download_order("654321", attempts=1)
        assert normal_pdf.read_bytes().startswith(b"%PDF-")
        assert driver.execute_script("return window.applied[0]") == "654321"
        page.configure_supply_filters("01/10/2026", "12/10/2026", requester, "")
        assert driver.execute_script("return window.applied[5]") == ""
        assert driver.execute_script("return window.applied[4]") == (
            "1221 - HERRERA PUENTE WILLAM DANIEL" if requester else ""
        )
        assert page.download_all_visible_results()[0].error is None
        driver.execute_script("window.emptyQuery = true")
        page.configure_supply_filters("01/10/2026", "12/10/2026", "", "")
        assert page.download_all_visible_results() == []
    finally:
        driver.quit()


@pytest.mark.parametrize("with_supplier", [True, False])
def test_supply_fallback_keeps_requester_and_authorizer(monkeypatch, tmp_path, with_supplier):
    from types import SimpleNamespace

    requester, authorizer = object(), object()
    fields = ([object()] if with_supplier else []) + [requester, authorizer]
    page = OrderPortalPage(SimpleNamespace(execute_script=lambda *args: None), tmp_path)
    monkeypatch.setattr(page, "_elements_now", lambda *args, **kwargs: fields)
    assert page._autocomplete_by_label("solicitante", -2) is requester
    assert page._autocomplete_by_label("autoriza", -1) is authorizer
