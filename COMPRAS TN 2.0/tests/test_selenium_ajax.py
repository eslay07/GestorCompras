from __future__ import annotations

import re
import time
from urllib.parse import quote

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By

from compras_tn.infrastructure.automation.downloads import OrderPortalPage
from compras_tn.infrastructure.automation.browser import create_corporate_browser
from compras_tn.infrastructure.automation.telcos import OperationCancelled, TasksPage


def test_menu_click_waits_for_intercepting_layer_without_js_click(chrome, tmp_path):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button id="query" onclick="this.dataset.blocked=String(!!document.getElementById('cover'));this.dataset.clicks=String(Number(this.dataset.clicks||0)+1)"><span>Consultas</span></button>
      <div id="cover" style="position:fixed;inset:0;z-index:999;background:#aaa"></div>
      <script>setTimeout(()=>document.getElementById('cover').remove(),1700)</script>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=5)
    page._click(((By.CSS_SELECTOR, '#query span'),), 'Consultas')
    button = chrome.find_element(By.ID, 'query')
    assert button.get_attribute('data-blocked') == 'false'
    assert button.get_attribute('data-clicks') == '1'


def test_late_queries_do_not_trigger_accesses(chrome, tmp_path):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button id="access" onclick="this.dataset.clicked='yes'">Accesos</button>
      <div id="menu"></div>
      <button id="orders" style="display:none" onclick="document.getElementById('form').innerHTML='<input placeholder=O/C>'">Consulta de Órdenes de Compra</button>
      <div id="form"></div>
      <script>setTimeout(()=>{
        const b=document.createElement('button');b.textContent='Consultas';
        b.onclick=()=>document.getElementById('orders').style.display='block';
        document.getElementById('menu').appendChild(b);
      },600)</script>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=3, login_timeout=3)
    page._navigate_shell_to_orders('dashboard')
    assert chrome.find_element(By.ID, 'access').get_attribute('data-clicked') is None
    assert chrome.find_element(By.CSS_SELECTOR, 'input[placeholder="O/C"]').is_displayed()


def test_toolbar_opens_clipped_sidebar_before_queries(chrome, tmp_path):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <mat-toolbar><button value="sidebarclosed" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1);document.getElementById('snav').style.width='260px'">
      <mat-icon>menu</mat-icon></button></mat-toolbar>
      <nav id="snav" style="width:64px;overflow:hidden">
      <button style="width:250px" onclick="document.getElementById('orders').style.display='block'">Consultas</button>
      <button id="orders" style="display:none;width:250px" onclick="document.getElementById('form').innerHTML='<input placeholder=O/C>'">Consulta de Órdenes de Compra</button>
      </nav><div id="form"></div>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=3)
    page._navigate_shell_to_orders('dashboard')
    assert chrome.find_element(By.CSS_SELECTOR, 'mat-toolbar button').get_attribute('data-clicks') == '1'
    assert chrome.find_element(By.CSS_SELECTOR, 'input[placeholder="O/C"]').is_displayed()


def test_opening_sidebar_is_not_toggled_closed(chrome, tmp_path):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <mat-toolbar><button value="sidebarclosed" onclick="this.dataset.clicked='yes'"><mat-icon>menu</mat-icon></button></mat-toolbar>
      <nav id="snav" class="mat-drawer-opened" style="width:260px;transform:translateX(-260px)">Consultas</nav>
      <script>setTimeout(()=>document.getElementById('snav').style.transform='none',600)</script>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=3)
    page._ensure_navigation_open()
    assert chrome.find_element(By.CSS_SELECTOR, 'mat-toolbar button').get_attribute('data-clicked') is None


def test_ready_click_does_not_wait_for_background_angular(chrome, tmp_path):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button id="query" onclick="this.dataset.clicked='yes'">Consultar</button>
      <script>window.getAllAngularTestabilities=()=>[{isStable:()=>false}];</script>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=2)
    page._click(((By.ID, 'query'),), 'Consultar', timeout=2)
    assert chrome.find_element(By.ID, 'query').get_attribute('data-clicked') == 'yes'


def test_side_menu_is_closed_before_date_and_single_save(chrome, tmp_path, monkeypatch):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <style>
      input,#save {position:absolute;left:100px;top:100px;width:200px;height:40px}
      #save {top:180px} #side {position:fixed;left:0;top:0;width:400px;height:400px;z-index:10;background:gray}
      #toggle {position:fixed;left:900px;top:10px;z-index:20}
      </style>
      <input name="fecha"><h4 id="number">N° de orden -</h4>
      <button id="save" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1);document.getElementById('number').textContent='N° de orden 400123'">Guardar</button>
      <div id="side" class="simple-sidenav__item-content">Menu</div>
      <button id="toggle" class="simple-sidenav__toggle" onclick="document.getElementById('side').style.display='none'">menu</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3, query_timeout=2)
    page._set_text('Fecha', '10/14/2026')
    assert chrome.find_element(By.NAME, 'fecha').get_attribute('value') == '10/14/2026'
    chrome.execute_script("document.getElementById('side').style.display='block'")
    page._verified_observation = 'Observacion verificada'
    monkeypatch.setattr(page, '_observation_matches', lambda _: True)
    assert page.save_once() == '400123'
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicks') == '1'


@pytest.fixture(scope="module")
def chrome(tmp_path_factory) -> webdriver.Chrome:
    try:
        driver = create_corporate_browser(tmp_path_factory.mktemp("browser-ajax"), True)
    except Exception as exc:
        pytest.skip(f"Chrome WebDriver no está disponible: {exc}")
    yield driver
    driver.quit()


def test_naf_solicita_never_matches_solicitantes(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <fieldset><legend><span>Solicitantes</span></legend>
        <div><label>Proveedor *</label><ng-select name="noProveedor"><input id="supplier" value="RUC VALIDADO"></ng-select></div>
        <div><label>Solicita *</label><ng-select name="noEmpleado"><input id="requester"></ng-select></div>
      </fieldset>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path)
    page._set_text('Solicita', 'SOLICITANTE CORRECTO')
    assert chrome.find_element(By.ID, 'supplier').get_attribute('value') == 'RUC VALIDADO'
    assert chrome.find_element(By.ID, 'requester').get_attribute('value') == 'SOLICITANTE CORRECTO'


def _load(driver: webdriver.Chrome, body: str, script: str) -> None:
    # Model the real numbered column, not an identifier embedded in row prose.
    pattern = r'<tr><td>([Tt]area (?:antigua )?)(\d+)([^<]*)</td></tr>'
    replacement = r'<tr><td>\2</td><td>\1\2\3</td></tr>'
    body = re.sub(pattern, replacement, body)
    script = re.sub(pattern, replacement, script)
    html = f"""
    <!doctype html><html><body>
      <input id="txtActividad" value="">
      <button id="btnConsultar" onclick="runQuery()">Consultar</button>
      <table id="gridTareas"><thead><tr><th>No. Tarea</th><th>Observación</th></tr></thead><tbody>{body}</tbody></table>
      <script>function runQuery() {{ {script} }}</script>
    </body></html>
    """
    driver.get("data:text/html;charset=utf-8," + quote(html))


def test_naf_date_validates_display_after_us_parser_blur(chrome, tmp_path):
    from datetime import datetime

    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <input name="fechaVence" onblur="const p=this.value.split('/'); this.value=p[1]+'/'+p[0]+'/'+p[2]">
      <button>Next</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path)
    page._set_date('Fecha de vencimiento', datetime(2026, 10, 12))
    assert chrome.find_element(By.NAME, 'fechaVence').get_attribute('value') == '12/10/2026'


def test_naf_observation_targets_its_panel_and_is_required_before_save(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import (
        GoodsPurchaseOrderPage,
        PurchaseOrderValidationError,
    )

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button role="tab" id="obsTab" aria-selected="true">Observaciones</button>
      <section role="tabpanel" aria-labelledby="detailTab"><textarea readonly id="description">ARTICULO ORIGINAL</textarea></section>
      <section role="tabpanel" aria-labelledby="obsTab"><textarea id="observation" aria-invalid="false"></textarea></section>
      <h4 id="number">N° de orden -</h4>
      <button id="save" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1); document.getElementById('number').textContent='N° de orden 400001'">Guardar</button>
      <button id="approve" onclick="this.dataset.clicked='yes'">check</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=2)
    with pytest.raises(PurchaseOrderValidationError, match='no se pulsó Guardar'):
        page.save_once()
    expected = 'TAREA #164448987//PEDIDO:S/N// SOLIC. PERSONA\nARTICULO 1 PROVEEDOR $233.62'
    page.fill_observation(expected)
    assert chrome.find_element(By.ID, 'description').get_attribute('value') == 'ARTICULO ORIGINAL'
    assert chrome.find_element(By.ID, 'observation').get_attribute('value') == expected
    assert page.save_once() == '400001'
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicks') == '1'
    assert chrome.find_element(By.ID, 'approve').get_attribute('data-clicked') is None
    chrome.find_element(By.ID, 'observation').clear()
    with pytest.raises(PurchaseOrderValidationError, match='no se pulsó Guardar'):
        page.save_once()
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicks') == '1'


def test_observation_limit_blocks_without_truncation_or_save(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import (
        GoodsPurchaseOrderPage,
        PurchaseOrderValidationError,
    )
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button role="tab" id="obsTab" aria-selected="true">Observaciones</button>
      <section role="tabpanel" aria-labelledby="obsTab"><textarea id="observation" maxlength="10"></textarea></section>
      <button id="save" onclick="this.dataset.clicked='yes'">Guardar</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=2)
    with pytest.raises(PurchaseOrderValidationError, match='supera el límite'):
        page.fill_observation('TAREA #164448987\nSEGUNDA TAREA')
    assert chrome.find_element(By.ID, 'observation').get_attribute('value') == ''
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicked') is None
    with pytest.raises(PurchaseOrderValidationError, match='no se pulsó Guardar'):
        page.save_once()


def test_replaced_heading_after_save_recovers_and_syncs_once(chrome, tmp_path, monkeypatch, repositories):
    from test_oc_critical_safety import setup_facade

    from compras_tn.infrastructure.automation.purchase_orders import (
        GoodsPurchaseOrderPage,
        PurchaseOrderValidationError,
        SeleniumPurchaseOrderGateway,
    )
    from compras_tn.paths import AppPaths

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button role="tab" id="obsTab" aria-selected="true">Observaciones</button>
      <section role="tabpanel" aria-labelledby="obsTab"><textarea id="observation"></textarea></section>
      <h4 id="number">N° de orden -</h4>
      <button id="save" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1);
        document.getElementById('number').outerHTML='<h4 id=number>N° de orden 375235</h4>'">Guardar</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, query_timeout=3)
    old_header = chrome.find_element(By.ID, 'number')
    real_elements = page._elements_now
    stale_injected = []
    def elements(locators, **kwargs):
        if (locators == page.ORDER_NUMBER and not stale_injected
                and chrome.find_element(By.ID, 'save').get_attribute('data-clicks')):
            stale_injected.append(True)
            return [old_header]
        return real_elements(locators, **kwargs)
    monkeypatch.setattr(page, '_elements_now', elements)
    monkeypatch.setattr(page, 'login_and_open_orders', lambda credentials: None)
    def fill(original):
        page.fill_observation('TAREA verificada')
        return original
    monkeypatch.setattr(page, 'fill', fill)
    facade = setup_facade(repositories, tmp_path)
    credentials = facade.login('ana', 'memory-only')
    original = facade.load_purchase_order_drafts()[0]
    writes = []
    def sync(draft, number):
        receipt = facade.settings.get('oc_receipts', facade._oc_receipt_keys(draft)[0])
        assert receipt['state'] == 'pending' and receipt['number'] == number
        writes.append(number)
    facade.sheets.record_purchase_order = sync
    gateway = SeleniumPurchaseOrderGateway(facade.settings, AppPaths.from_root(tmp_path))
    # The fixture owns Chrome; the gateway still executes its full save/callback flow.
    from types import SimpleNamespace
    monkeypatch.setattr(gateway, '_create_driver', lambda _: SimpleNamespace(quit=lambda: None))
    monkeypatch.setattr(gateway, '_page', lambda _: page)
    result = gateway.preload(credentials, [original], before_save=facade._prepare_oc_save, on_saved=facade._sync_saved_oc)
    assert result.items[0].payload['sheet_written'] is True
    assert stale_injected == [True]
    assert writes == ['375235']
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicks') == '1'
    with pytest.raises(PurchaseOrderValidationError, match='no se pulsó Guardar'):
        page.save_once()


def test_naf_waits_for_marked_option_and_numeric_enter(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <ng-select name="noEmpleado"><span class="ng-value-label"></span><input id="requester"></ng-select>
      <mat-form-field><mat-label>MENSUAL</mat-label><input type="number" id="monthly" onkeydown="if(event.key==='Enter') document.getElementById('add').disabled=false"></mat-form-field>
      <button id="add" disabled>Agregar un nuevo registro</button>
      <script>
      const field=document.getElementById('requester'); let timer;
      field.oninput=()=>{clearTimeout(timer); timer=setTimeout(()=>{
        if(document.querySelector('ng-dropdown-panel')) return;
        const panel=document.createElement('ng-dropdown-panel');
        panel.innerHTML='<div class="ng-option ng-option-marked">12 - OTRA PERSONA</div><div class="ng-option">1542 - PEREZ BARBERAN MARIA BELEN</div>';
        document.body.append(panel);
      },300)};
      field.onkeydown=e=>{const panel=document.querySelector('ng-dropdown-panel'); if(!panel)return;
        if(e.key==='ArrowDown'){panel.children[0].classList.remove('ng-option-marked');panel.children[1].classList.add('ng-option-marked')}
        if(e.key==='Enter'){
          field.parentElement.querySelector('.ng-value-label').textContent=panel.querySelector('.ng-option-marked').textContent.replace(/^\\d+ - /,'');
          field.value=''; panel.remove();
        }
      };
      </script>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=5)
    page._select_exact('Solicita', 'PEREZ BARBERAN MARIA BELEN', error_code='solicitante')
    assert chrome.find_element(By.CSS_SELECTOR, '.ng-value-label').text == 'PEREZ BARBERAN MARIA BELEN'
    assert not chrome.find_element(By.ID, 'add').is_enabled()
    page._set_text('Mensual', '1')
    assert chrome.find_element(By.ID, 'add').is_enabled()


@pytest.mark.parametrize('already_selected,replace_on_close', [(True, False), (False, False), (False, True)])
def test_payment_frequency_commits_then_closes_before_monthly(chrome, tmp_path, already_selected, replace_on_close):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    html = '''
      <ng-select name="idTipoFrecuencia"><span class="ng-value-label">INITIAL</span><input id="frequency" readonly aria-expanded="false"></ng-select>
      <mat-form-field><mat-label>Mensual</mat-label><input id="monthly" type="number" disabled></mat-form-field>
      <button id="save" onclick="window.saves++">Guardar</button>
      <ng-dropdown-panel id="unrelated"><div class="ng-option">OTRO CATÁLOGO</div></ng-dropdown-panel>
      <script>
      window.opens=0; window.enters=0; window.saves=0;
      const select=document.querySelector('ng-select');
      function bind(field){
        field.onclick=()=>{
          if(document.getElementById('frequencyPanel')) return;
          window.opens++;
          select.classList.add('ng-select-opened'); field.setAttribute('aria-expanded','true');
          const panel=document.createElement('ng-dropdown-panel'); panel.id='frequencyPanel';
          panel.innerHTML='<div class="ng-option">DIARIA</div><div class="ng-option ng-option-marked">MENSUAL</div>';
          document.body.append(panel);
        };
        field.onkeydown=event=>{
          if(event.key==='Enter'){
            window.enters++; select.querySelector('.ng-value-label').textContent='MENSUAL';
            // NAF may retain the panel after an already-selected option is confirmed.
          }
          if(event.key==='Escape'){
            document.getElementById('frequencyPanel')?.remove();
            select.classList.remove('ng-select-opened');field.setAttribute('aria-expanded','false');
            if(REPLACE){const next=field.cloneNode();field.replaceWith(next);bind(next);}
          }
          if(event.key==='Tab' && select.querySelector('.ng-value-label').textContent==='MENSUAL')
            document.getElementById('monthly').disabled=false;
        };
      }
      bind(document.getElementById('frequency'));
      document.getElementById('monthly').onkeydown=e=>{if(e.key==='Enter')window.monthlyConfirmed=true;};
      </script>
    '''.replace('INITIAL', 'MENSUAL' if already_selected else '').replace('REPLACE', 'true' if replace_on_close else 'false')
    chrome.get('data:text/html;charset=utf-8,' + quote(html))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=2)
    page._select_exact('Frecuencia de pago', 'MENSUAL', error_code='catalogo_naf_no_encontrado')
    page._set_text('Mensual', '1')
    assert chrome.execute_script('return window.enters') == (0 if already_selected else 1)
    assert chrome.execute_script('return window.opens') == (0 if already_selected else 1)
    assert chrome.execute_script('return window.monthlyConfirmed') is True
    assert chrome.execute_script('return window.saves') == 0
    assert not chrome.find_elements(By.ID, 'frequencyPanel')
    assert chrome.find_element(By.ID, 'unrelated').is_displayed()


def test_frequency_search_text_is_not_a_committed_selection(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <ng-select name="idTipoFrecuencia"><span class="ng-value-label">DIARIA</span>
      <input id="frequency" value="MENSUAL"></ng-select>
      <ng-dropdown-panel><div class="ng-option ng-option-marked">MENSUAL</div></ng-dropdown-panel>
      <button id="save" onclick="this.dataset.clicked='yes'">Guardar</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=1)
    with pytest.raises(TimeoutError, match='confirmar el valor seleccionado'):
        page._select_exact('Frecuencia de pago', 'MENSUAL', error_code='catalogo_naf_no_encontrado')
    assert chrome.find_element(By.CSS_SELECTOR, '.ng-value-label').text == 'DIARIA'
    assert chrome.find_element(By.ID, 'save').get_attribute('data-clicked') is None


def test_hidden_naf_session_validation_dialog_retries_automatically(chrome, tmp_path):
    from compras_tn.infrastructure.automation.downloads import OrderPortalPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <div class="swal2-popup" role="dialog">¿Volver a intentar? No se pudo validar la sesión
        <button class="swal2-confirm" onclick="this.parentElement.remove();document.body.insertAdjacentHTML('beforeend','<input id=order>')">Si</button>
        <button>No</button>
      </div>
    '''))
    page = OrderPortalPage(chrome, tmp_path, element_timeout=3)
    page.ORDER_INPUT = ((By.ID, "order"),)
    assert page._wait_for_shell(3) == "orders"


def test_telcos_custom_autocomplete_waits_then_commits_with_keyboard(chrome):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <input id="txtDepartment"><input id="txtEmpleado"><input id="txtDatetimepickerEjecReasigna" value="2026-09-12"><select id="hour"><option>00:29</option></select>
      <script>
      for (const [id,label] of [['txtDepartment','Bodega'],['txtEmpleado','Responsable de demostración']]) {
        const field=document.getElementById(id); let timer, active=false;
        field.oninput=()=>{ clearTimeout(timer); active=false;
          document.getElementById(id+'autocomplete-list')?.remove();
          timer=setTimeout(()=>{ const list=document.createElement('div');
            list.id=id+'autocomplete-list'; list.className='autocomplete-items';
            list.innerHTML='<div><strong>'+label+'</strong><input type="hidden"></div>';
            field.after(list); },250);
        };
        field.onkeydown=e=>{ if(e.key==='ArrowDown') {active=true; document.querySelector('#'+id+'autocomplete-list > div').classList.add('autocomplete-active');}
          if(e.key==='Enter' && active) { e.preventDefault(); field.value=label;
            field.dataset.selected='yes'; document.getElementById(id+'autocomplete-list').remove(); }
        };
      }
      </script>
    '''))
    page = TasksPage(chrome)
    page.select_autocomplete(((By.ID, 'txtDepartment'),), 'BODEGA', 'Departamento')
    assert chrome.find_element(By.ID, 'txtDepartment').get_attribute('data-selected') == 'yes'
    page.select_autocomplete(((By.ID, 'txtEmpleado'),), 'Responsable de demostración', 'Empleado')
    assert chrome.find_element(By.ID, 'txtEmpleado').get_attribute('data-selected') == 'yes'
    assert chrome.switch_to.active_element.get_attribute('id') == 'hour'
    assert chrome.find_element(By.ID, 'txtDatetimepickerEjecReasigna').get_attribute('value') == '2026-09-12'


@pytest.mark.parametrize('monthly_label', ['MENSUAL', 'Mensual'])
def test_monthly_waits_for_replaced_disabled_control_without_retyping(chrome, tmp_path, monthly_label):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <mat-form-field id="field"><mat-label>MENSUAL</mat-label><input type="number" disabled></mat-form-field><button>Next</button>
      <script>setTimeout(()=>{
        document.getElementById('field').innerHTML='<mat-label>MENSUAL</mat-label><input id="ready" type="number">';
        const e=document.getElementById('ready');
        e.oninput=()=>{e.dataset.writes=String(Number(e.dataset.writes||0)+1)};
        e.onkeydown=event=>{if(event.key==='Enter')e.dataset.confirmed='yes'};
      },700);</script>
    '''.replace('<mat-label>MENSUAL</mat-label>', f'<mat-label>{monthly_label}</mat-label>')))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3)
    page._set_text('Mensual', '1')
    field = chrome.find_element(By.ID, 'ready')
    assert field.get_attribute('value') == '1'
    assert field.get_attribute('data-writes') == '1'
    assert field.get_attribute('data-confirmed') == 'yes'


def test_telcos_already_active_option_is_not_skipped(chrome):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <input id="txtDepartment" oninput="document.getElementById('txtDepartmentautocomplete-list').style.display='block'">
      <div id="txtDepartmentautocomplete-list"><div class="autocomplete-active">Bodega</div><div>Otra</div></div><button>Next</button>
      <script>document.getElementById('txtDepartment').onkeydown=e=>{
        if(e.key==='ArrowDown') document.querySelector('.autocomplete-active').classList.remove('autocomplete-active');
        if(e.key==='Enter' && document.querySelector('.autocomplete-active')){
          e.target.value='Bodega';e.target.dataset.selected='yes';document.getElementById('txtDepartmentautocomplete-list').remove();
        }
      };</script>
    '''))
    TasksPage(chrome).select_autocomplete(((By.ID, 'txtDepartment'),), 'BODEGA', 'Departamento')
    assert chrome.find_element(By.ID, 'txtDepartment').get_attribute('data-selected') == 'yes'


def test_telcos_reports_server_usr_creacion_error_without_retry(chrome):
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button id="btnGrabarReasignaTarea" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1);document.getElementById('error').style.display='block'">Guardar</button>
      <div id="error" class="alert-danger" style="display:none">ORA-01400 USR_CREACION nulo</div>
    '''))
    with pytest.raises(ValueError, match='USR_CREACION'):
        TasksPage(chrome).save_reassignment()
    assert chrome.find_element(By.ID, 'btnGrabarReasignaTarea').get_attribute('data-clicks') == '1'


def test_consult_waits_for_slow_ajax_and_expected_number(chrome: webdriver.Chrome) -> None:
    _load(
        chrome,
        "<tr><td>tarea antigua 111</td></tr>",
        "setTimeout(() => { document.querySelector('#gridTareas tbody').innerHTML = '<tr><td>Tarea 987654 lista</td></tr>'; }, 550);",
    )
    started = time.monotonic()
    TasksPage(chrome).consult("987654")
    assert time.monotonic() - started >= 0.45


def test_consult_with_hidden_datatables_header(chrome: webdriver.Chrome) -> None:
    _load(chrome, "<tr><td>tarea antigua 111</td></tr>",
          "setTimeout(() => { document.querySelector('#gridTareas tbody').innerHTML = '<tr><td>Tarea 162841741 lista</td></tr>'; }, 150);")
    chrome.execute_script("""
        const header = document.querySelector('#gridTareas thead');
        header.style.display = 'none';
        header.querySelector('th').innerHTML = 'No.<br>Tarea';
    """)
    page = TasksPage(chrome, query_timeout=3)
    page.consult("162841741")
    assert page.current_task == "162841741"


@pytest.mark.parametrize("dialog_class,button_class", [("sweet-alert", "confirm"), ("swal2-popup", "swal2-confirm")])
def test_naf_company_waits_for_delayed_ok_despite_visible_menu(chrome, tmp_path, dialog_class, button_class):
    html = f'''<html><body>
        <button id="queries">Consultas</button>
        <section id="company"><input id="companyInput"><button id="option">TELCONET S.A.</button>
        <button id="choose" onclick="setTimeout(showConfirmation,900)">Elegir</button></section>
        <script>
        function showConfirmation() {{
          const modal = document.createElement('div'); modal.className='{dialog_class}';
          modal.innerHTML='<p>Transacción realizada correctamente</p><button class="{button_class}" onclick="confirmed()">OK</button>';
          document.body.appendChild(modal);
        }}
        function confirmed() {{
          document.querySelector('.{dialog_class}').remove();
          document.getElementById('company').remove();
          document.body.insertAdjacentHTML('beforeend','<input id="order">');
        }}
        </script></body></html>'''
    chrome.get("data:text/html;charset=utf-8," + quote(html))
    page = OrderPortalPage(chrome, tmp_path)
    page.COMPANY_INPUT = ((By.ID, "companyInput"),)
    page.TELCONET_OPTION = ((By.ID, "option"),)
    page.CHOOSE_COMPANY = ((By.ID, "choose"),)
    page.QUERIES = ((By.ID, "queries"),)
    page.ORDER_INPUT = ((By.ID, "order"),)
    page._select_company()
    assert chrome.find_elements(By.ID, "order")
    assert not chrome.find_elements(By.ID, "companyInput")


def test_consult_does_not_accept_a_stale_row_even_if_number_matches(chrome: webdriver.Chrome) -> None:
    _load(
        chrome,
        "<tr><td>Tarea 55555 anterior</td></tr>",
        "setTimeout(() => { document.querySelector('#gridTareas tbody').innerHTML = '<tr><td>Tarea 55555 nueva</td></tr>'; }, 500);",
    )
    started = time.monotonic()
    TasksPage(chrome).consult("55555")
    assert time.monotonic() - started >= 0.4


def test_consult_classifies_an_explicit_empty_result(chrome: webdriver.Chrome) -> None:
    _load(
        chrome,
        "<tr><td>Tarea anterior 111</td></tr>",
        "setTimeout(() => { document.querySelector('#gridTareas tbody').innerHTML = '<tr><td class=\"dataTables_empty\">Sin resultados</td></tr>'; }, 250);",
    )
    with pytest.raises(LookupError, match="no devolvió resultados"):
        TasksPage(chrome).consult("99999")


def test_consult_does_not_accept_an_identifier_that_is_only_a_prefix(
    chrome: webdriver.Chrome,
) -> None:
    _load(
        chrome,
        "<tr><td>Tarea 1234 antigua</td></tr>",
        "setTimeout(() => { document.querySelector('#gridTareas tbody').innerHTML = '<tr><td>Tarea 123 correcta</td></tr>'; }, 500);",
    )
    started = time.monotonic()
    TasksPage(chrome).consult("123")
    assert time.monotonic() - started >= 0.4


def test_consult_ignores_unrelated_page_activity_and_keeps_stale_result(
    chrome: webdriver.Chrome,
) -> None:
    _load(
        chrome,
        "<tr><td>Tarea 444 ya visible</td></tr>",
        "document.body.dataset.otherActivity = 'completed';",
    )
    with pytest.raises(TimeoutError, match="resultado correspondiente"):
        TasksPage(chrome, query_timeout=1).consult("444")


def test_consult_does_not_treat_a_temporary_empty_row_as_final(
    chrome: webdriver.Chrome,
) -> None:
    _load(
        chrome,
        "<tr><td>Tarea anterior 111</td></tr>",
        """
        setTimeout(() => {
          document.querySelector('#gridTareas tbody').innerHTML =
            '<tr><td class="dataTables_empty">Consultando...</td></tr>';
        }, 150);
        setTimeout(() => {
          document.querySelector('#gridTareas tbody').innerHTML =
            '<tr><td>Tarea 777 resultado final</td></tr>';
        }, 900);
        """,
    )
    TasksPage(chrome).consult("777")


def test_click_waits_until_blocking_overlay_disappears(chrome: webdriver.Chrome) -> None:
    html = """
    <!doctype html><html><body>
      <div class="blockUI blockOverlay"
           style="position:fixed;inset:0;background:#fff;z-index:10"></div>
      <button id="target" onclick="this.dataset.clicked='yes'">Continuar</button>
      <script>
        setTimeout(() => document.querySelector('.blockOverlay').remove(), 500);
      </script>
    </body></html>
    """
    chrome.get("data:text/html;charset=utf-8," + quote(html))
    started = time.monotonic()
    page = TasksPage(chrome)
    page.click((("id", "target"),), "Continuar")
    assert time.monotonic() - started >= 0.4
    assert chrome.find_element("id", "target").get_attribute("data-clicked") == "yes"


def test_set_text_recovers_when_the_input_is_replaced(chrome: webdriver.Chrome) -> None:
    html = """
    <!doctype html><html><body>
      <input id="replaceable" oninput="replaceOnce(this)">
      <script>
        let replaced = false;
        function replaceOnce(input) {
          if (replaced) return;
          replaced = true;
          const next = input.cloneNode();
          next.value = '';
          input.replaceWith(next);
        }
      </script>
    </body></html>
    """
    chrome.get("data:text/html;charset=utf-8," + quote(html))
    TasksPage(chrome).set_text((("id", "replaceable"),), "987654", "el número")
    assert chrome.find_element("id", "replaceable").get_attribute("value") == "987654"


def test_wait_can_be_cancelled_without_waiting_for_timeout(chrome: webdriver.Chrome) -> None:
    chrome.get("data:text/html,<html><body></body></html>")
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(OperationCancelled):
        TasksPage(chrome, cancelled=cancelled).find(
            (("id", "never-exists"),),
            "un elemento inexistente",
            timeout=20,
        )
    assert checks < 10


@pytest.mark.parametrize("glyph", ["play", "step-forward"])
def test_workflow_opens_assigned_or_paused_task_exact_row(chrome, glyph):
    chrome.get("data:text/html;charset=utf-8," + quote(f"""
      <table id="gridTareas"><thead><tr><th>No. Tarea</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
      <tr><td>100</td><td>Asignada</td><td><button onclick="document.body.dataset.wrong='yes'"><span class="glyphicon-play">Wrong</span></button></td></tr>
      <tr><td>200</td><td>Asignada</td><td><button onclick="document.getElementById('txtObservacionTarea').style.display='block'"><span class="glyphicon-{glyph}">Correct</span></button></td></tr>
      </tbody></table><textarea id="txtObservacionTarea" style="display:none"></textarea>
    """))
    page = TasksPage(chrome, timeout=2, long_timeout=2)
    page.current_task = "200"
    page.resume()
    assert chrome.find_element(By.ID, "txtObservacionTarea").is_displayed()
    assert chrome.find_element(By.TAG_NAME, "body").get_attribute("data-wrong") is None


def test_pause_uses_shared_accept_button_but_requires_visible_pause_form(chrome):
    from compras_tn.infrastructure.automation.telcos import SeleniumActionExecutor
    chrome.get("data:text/html;charset=utf-8," + quote("""
      <div id="modalEjecucionTarea">
        <select id="cmbMotivoPausa"><option value="1641">Cotización</option></select>
        <button id="btnGrabarEjecucionTarea" onclick="document.getElementById('btnSmsCustomOk').style.display='block';this.dataset.saved='yes'">Aceptar</button>
      </div><button id="btnSmsCustomOk" style="display:none">OK</button>
    """))
    page = TasksPage(chrome, timeout=2, long_timeout=2)
    executor = SeleniumActionExecutor(page, object(), object())
    executor.action_aceptar_pausa({}, {})
    assert chrome.find_element(By.ID, "btnGrabarEjecucionTarea").get_attribute("data-saved") == "yes"
    chrome.execute_script("document.getElementById('cmbMotivoPausa').style.display='none'")
    with pytest.raises(RuntimeError, match="no está listo"):
        executor.action_aceptar_pausa({}, {})


def test_task_data_is_reusable_and_preflight_defers_values_read_from_telcos(chrome):
    from compras_tn.domain.models import FlowStep, WorkflowDefinition
    from compras_tn.infrastructure.automation.telcos import SeleniumActionExecutor
    chrome.get("data:text/html;charset=utf-8," + quote("""
      <table id="gridTareas"><thead><tr><th>No. Tarea</th><th>Estado</th><th>Responsable Asignado</th><th>Tarea</th></tr></thead><tbody>
      <tr><td>100</td><td>Asignada</td><td>Persona incorrecta</td><td>Otra tarea</td></tr>
      <tr><td>200</td><td>Pausada</td><td>Responsable correcto</td><td>Compras por pedidos</td></tr>
      </tbody></table>
    """))
    page = TasksPage(chrome, timeout=2, long_timeout=2)
    page.current_task = "200"
    executor = SeleniumActionExecutor(page, object(), object())
    workflow = WorkflowDefinition(name="Lectura", steps=[
        FlowStep(action_id="seleccionar_tarea"),
        FlowStep(action_id="capturar_datos_tarea"),
        FlowStep(action_id="definir_variable", params={"nombre": "resumen", "valor": "{telcos_responsable}"}),
    ])
    executor.preflight(workflow, {"task_number": "200"})
    context = {}
    executor.action_capturar_datos_tarea({}, context)
    assert context["telcos_responsable"] == "Responsable correcto"
    assert context["telcos_estado"] == "Pausada"
    assert context["telcos_numero_tarea"] == "200"
    assert context["telcos_caso"] == ""  # No inventa valores opcionales ausentes.


@pytest.mark.parametrize("hidden", [True, False])
def test_file_selection_replaces_hidden_or_visible_input(chrome, tmp_path, hidden):
    style = 'display:none' if hidden else ''
    chrome.get('data:text/html;charset=utf-8,' + quote(f'<input type="file" name="archivos[]" multiple style="{style}">'))
    page = TasksPage(chrome, timeout=2, long_timeout=2)
    first = tmp_path / 'cotizacion.pdf'
    second = tmp_path / 'ficha.txt'
    first.write_bytes(b'first')
    second.write_bytes(b'second')
    context = {}
    page.select_file(first, context)
    page.select_file(second, context)
    assert chrome.execute_script('return Array.from(document.querySelector("input").files, f=>f.name)') == ['ficha.txt']
    assert context['archivo_seleccionado'] == str(second.resolve())


def test_approval_send_reads_only_pending_and_paginates(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <button mattooltip="Enviar aprobación" onclick="this.dataset.sent=String(Number(this.dataset.sent||0)+1);document.getElementById('flow').style.display='block'">Enviar</button>
      <button id="flow" mattooltip="Ver flujo de aprobación" style="display:none" onclick="document.getElementById('approval').style.display='block'">Ver</button>
      <div id="approval" role="dialog" tabindex="-1" style="display:none" onkeydown="if(event.key==='Escape')this.style.display='none'">
        <h2>N° orden: 377630</h2><table><tbody id="rows">
          <tr><td>1</td><td>165 - PERSONA UNO COMPLETO</td><td>-</td><td>POR APROBAR</td></tr>
          <tr><td>2</td><td>200 - YA APROBADO</td><td>-</td><td>APROBADO</td></tr>
        </tbody></table>
        <button class="mat-paginator-navigation-next" onclick="document.getElementById('rows').innerHTML='<tr><td>3</td><td>50 - PERSONA DOS COMPLETO</td><td>-</td><td>POR AUTORIZAR</td></tr>';this.disabled=true">Next</button>
      </div>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3, query_timeout=3)
    page._saved_numbers = lambda: {'377630'}
    stages = []
    names = page.send_and_read_approval('377630', lambda state, names: stages.append(state))
    assert names == ['PERSONA UNO COMPLETO', 'PERSONA DOS COMPLETO']
    assert stages == ['sending', 'sent', 'read']
    assert chrome.find_element(By.CSS_SELECTOR, '[mattooltip="Enviar aprobación"]').get_attribute('data-sent') == '1'


def test_telcos_finalizer_rejects_unclosed_upload_confirmation(chrome):
    from compras_tn.infrastructure.automation.telcos import SeleniumActionExecutor
    chrome.get('data:text/html;charset=utf-8,' + quote('<div class="modal in"><button id="btnSmsCustomOk">OK</button></div>'))
    page = TasksPage(chrome, timeout=2, long_timeout=2)
    executor = SeleniumActionExecutor(page, object(), object())
    with pytest.raises(RuntimeError, match='ventana abierta'):
        executor.finish_task({})
    chrome.execute_script('document.querySelector("div").remove()')
    executor.finish_task({})


@pytest.mark.parametrize('state,receipt,expected', [('CREADO','pending',['send','flow']), ('PENDIENTE','pending',['flow']), ('CREADO','ambiguous',[])])
@pytest.mark.parametrize('icon_only', [False, True])
def test_approval_visible_icon_is_not_evidence_of_send(chrome, tmp_path, state, receipt, expected, icon_only):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage, PurchaseOrderValidationError
    html = '''
      <div id="state">C | INITIAL</div>
      <button mattooltip="Enviar aprobación" onclick="window.events.push('send');setTimeout(()=>document.getElementById('state').textContent='P | PENDIENTE',300)">Enviar</button>
      <button mattooltip="Ver flujo de aprobación" onclick="window.events.push('flow');document.getElementById('approval').style.display='block';setTimeout(()=>document.getElementById('rows').innerHTML='<tr><td>1</td><td>165 - PERSONA COMPLETA</td><td>-</td><td>POR APROBAR</td></tr>',400)">Ver</button>
      <div id="approval" role="dialog" tabindex="-1" style="display:none" onkeydown="if(event.key==='Escape')this.style.display='none'">
        <h2>N° orden: 377657</h2><table><tbody id="rows"></tbody></table>
      </div><script>window.events=[];</script>
    '''.replace('INITIAL', state)
    if icon_only:
        html = html.replace('mattooltip="Enviar aprobación"', 'data-send="approval"').replace('>Enviar</button>', '><mat-icon>check</mat-icon></button>')
    chrome.get('data:text/html;charset=utf-8,' + quote(html))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3, query_timeout=3)
    page._saved_numbers = lambda: {'377657'}
    stages = []
    if receipt == 'ambiguous':
        with pytest.raises(PurchaseOrderValidationError, match='no se repitió'):
            page.send_and_read_approval('377657', lambda stage, names: stages.append(stage), receipt)
        assert not stages
    else:
        assert page.send_and_read_approval('377657', lambda stage, names: stages.append(stage), receipt) == ['PERSONA COMPLETA']
        assert stages == (['sending','sent','read'] if state == 'CREADO' else ['read'])
    assert chrome.execute_script('return window.events') == expected


def test_approval_does_not_open_flow_until_created_state_changes(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <div>C | CREADO</div>
      <button mattooltip="Enviar aprobación" onclick="this.dataset.clicks=String(Number(this.dataset.clicks||0)+1)">Enviar</button>
      <button mattooltip="Ver flujo de aprobación" onclick="this.dataset.opened='yes'">Ver</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=1, query_timeout=1)
    page._saved_numbers = lambda: {'377657'}
    stages = []
    with pytest.raises(TimeoutError):
        page.send_and_read_approval('377657', lambda state, names: stages.append(state), 'pending')
    assert stages == ['sending', 'ambiguous']
    assert chrome.find_element(By.CSS_SELECTOR, '[mattooltip="Enviar aprobación"]').get_attribute('data-clicks') == '1'
    assert chrome.find_element(By.CSS_SELECTOR, '[mattooltip="Ver flujo de aprobación"]').get_attribute('data-opened') is None


def test_orchestrator_relocates_stale_task_state_before_opening_upload(chrome):
    from selenium.common.exceptions import StaleElementReferenceException
    from compras_tn.infrastructure.automation.telcos import SeleniumActionExecutor
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <table id="gridTareas"><thead><tr><th>No Tarea</th><th>Estado</th></tr></thead>
      <tbody><tr><td>163826137</td><td>EN EJECUCION</td></tr></tbody></table>
      <input type=file name="archivos[]" style="display:none">
    '''))
    page = TasksPage(chrome, timeout=3, long_timeout=3)
    page.current_task = '163826137'
    original = page.row_value
    reads = []
    def refresh(row, names):
        if names == {'ESTADO'} and not reads:
            reads.append('stale')
            chrome.execute_script('const r=document.querySelector("tbody tr");r.replaceWith(r.cloneNode(true))')
            raise StaleElementReferenceException('AJAX replaced row')
        return original(row, names)
    page.row_value = refresh
    opened = []
    page.open_upload = lambda: opened.append('opened')
    page.remote_file_hashes = lambda: set()
    executor = SeleniumActionExecutor(page, object(), object())
    executor.execute('abrir_subida_archivo', {}, {})
    assert reads == ['stale'] and opened == ['opened']
    with pytest.raises(RuntimeError, match='sigue en ejecución'):
        executor.finish_task({})


def test_orchestrator_waits_for_delayed_overlay_before_action(chrome):
    from compras_tn.infrastructure.automation.telcos import SeleniumActionExecutor
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <script>setTimeout(()=>{
        const cover=document.createElement('div');cover.className='blockUI blockOverlay';
        cover.style='position:fixed;inset:0';document.body.appendChild(cover);
        setTimeout(()=>{cover.remove();document.body.dataset.ready='yes'},350);
      },150)</script>
    '''))
    page = TasksPage(chrome, timeout=3, long_timeout=3)
    calls=[]
    page.open_upload=lambda: calls.append(chrome.execute_script('return document.body.dataset.ready'))
    page.remote_file_hashes=lambda: set()
    SeleniumActionExecutor(page, object(), object()).execute('abrir_subida_archivo', {}, {})
    assert calls == ['yes']


@pytest.mark.parametrize('secure_crypto', [True, False])
def test_telcos_existing_files_hashes_read_all_pages_and_close(chrome, secure_crypto):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    content=b'existing order bytes'
    other=b'another attachment'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path in ('/one.pdf','/two.pdf'):
                body=content if self.path=='/one.pdf' else other
                kind='application/pdf'
            else:
                body=b'''<button id=view onclick="document.getElementById('modalVerArchivos').style.display='block'">Ver archivos</button>
                <div id=modalVerArchivos style="display:none"><table><tbody id=rows><tr><td><a href='/one.pdf'>ORDEN.pdf</a></td></tr></tbody></table>
                <button class='paginate_button next' onclick="document.querySelector('#rows a').href='/two.pdf';this.classList.add('disabled');this.disabled=true">Next</button>
                <button class=close onclick="this.parentNode.style.display='none'">Cerrar</button></div>'''
                kind='text/html'
            self.send_response(200); self.send_header('Content-Type', kind); self.end_headers(); self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        chrome.get(f'http://127.0.0.1:{server.server_port}/')
        if not secure_crypto:
            chrome.execute_script("Object.defineProperty(window.crypto, 'subtle', {value:undefined})")
        page=TasksPage(chrome,timeout=3,long_timeout=3)
        page._row_control=lambda *a,**k: chrome.find_element(By.ID,'view')
        assert page.remote_file_hashes()=={hashlib.sha256(content).hexdigest(),hashlib.sha256(other).hexdigest()}
        assert not chrome.find_element(By.ID,'modalVerArchivos').is_displayed()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)

@pytest.mark.parametrize('kind', ['onclick_url','dynamic_download','empty_custom'])
def test_telcos_file_list_supports_buttons_and_empty_placeholder(chrome, kind):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    data=b'order already uploaded'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.startswith('/file.pdf'):
                body=data;mime='application/pdf'
            else:
                if kind=='empty_custom':
                    row='<tr><td colspan=5>No se han cargado archivos para esta tarea</td></tr>'
                elif kind=='onclick_url':
                    row='''<tr><td>ORDEN.pdf</td><td><button onclick="window.open('/file.pdf')">Descargar</button></td></tr>'''
                else:
                    row='''<tr><td>ORDEN.pdf</td><td><button title=Descargar onclick="descargarArchivo(17)">Archivo</button></td></tr>'''
                html='''<button id=view onclick="document.getElementById('modalVerArchivos').style.display='block'">Ver</button>
                <div id=modalVerArchivos style="display:none"><table><tbody>'''+row+'''</tbody></table>
                <button class=close onclick="this.parentNode.style.display='none'">Cerrar</button></div>
                <script>function descargarArchivo(id){const p=window.open('');setTimeout(()=>p.location.href='/file.pdf?id='+id,100)}</script>'''
                body=html.encode();mime='text/html'
            self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        chrome.get(f'http://127.0.0.1:{server.server_port}/')
        page=TasksPage(chrome,timeout=3,long_timeout=3)
        page._row_control=lambda *a,**k: chrome.find_element(By.ID,'view')
        assert page.remote_file_hashes()==(set() if kind=='empty_custom' else {hashlib.sha256(data).hexdigest()})
        assert len(chrome.window_handles)==1
        assert chrome.execute_script('return !window.__comprasFileProbe')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)

@pytest.mark.parametrize('mode', ['cross_origin', 'viewer', 'login_html'])
def test_telcos_download_fallback_handles_session_and_viewer(chrome, tmp_path, mode):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    payload=b'%PDF-1.7 same order content'
    back_port=[0]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            code=200; mime='text/html'
            if self.path=='/document':
                if 'test_session=authenticated' not in (self.headers.get('Cookie') or ''):
                    code=401;body=b'Unauthorized'
                else:
                    body=payload;mime='application/pdf'
            elif self.path=='/viewer':
                body=b'<html><iframe src="/document"></iframe></html>'
            elif self.path=='/login':
                body=b'<html><form><input type=password></form></html>'
            else:
                target=f'http://127.0.0.1:{back_port[0]}/document' if mode=='cross_origin' else '/viewer' if mode=='viewer' else '/login'
                body=('''<button id=view onclick="document.getElementById('modalVerArchivos').style.display='block'">Ver</button>
                <div id=modalVerArchivos style="display:none"><table><tbody><tr><td><a href="'''+target+'''">ORDEN 377630.pdf</a></td></tr></tbody></table>
                <button class=close onclick="this.parentNode.style.display='none'">Cerrar</button></div>''').encode()
            self.send_response(code);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(body)
    servers=[ThreadingHTTPServer(('127.0.0.1',0),Handler) for _ in range(2)]
    back_port[0]=servers[1].server_port
    threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers]
    for thread in threads: thread.start()
    try:
        chrome.get(f'http://127.0.0.1:{servers[0].server_port}/')
        chrome.add_cookie({'name':'test_session','value':'authenticated','path':'/'})
        page=TasksPage(chrome,timeout=3,long_timeout=3)
        page.file_list_diagnostic_path=tmp_path/'files.html'
        page._row_control=lambda *a,**k: chrome.find_element(By.ID,'view')
        if mode=='login_html':
            with pytest.raises(RuntimeError,match='HTML de visor o inicio de sesión'):
                page.remote_file_hashes()
            assert (tmp_path/'files.html').is_file()
            assert (tmp_path/'files.json').is_file()
        else:
            assert page.remote_file_hashes()=={hashlib.sha256(payload).hexdigest()}
        assert not chrome.find_element(By.ID,'modalVerArchivos').is_displayed()
    finally:
        for server in servers: server.shutdown();server.server_close()
        for thread in threads: thread.join(timeout=2)


def test_frequency_recovers_when_naf_ignores_enter(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage

    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <ng-select name="idTipoFrecuencia" class="ng-select-opened">
        <span class="ng-value-label"></span><input readonly aria-expanded="true">
      </ng-select>
      <ng-dropdown-panel><div class="ng-option ng-option-marked"
        onclick="document.querySelector('.ng-value-label').textContent='MENSUAL';window.picks++">MENSUAL</div></ng-dropdown-panel>
      <button onclick="window.saves++">Guardar</button>
      <script>
        window.picks=0; window.saves=0;
        document.querySelector('input').onkeydown=e=>{
          if(e.key==='Escape'){
            document.querySelector('ng-dropdown-panel').remove();
            document.querySelector('ng-select').classList.remove('ng-select-opened');
            e.target.setAttribute('aria-expanded','false');
          }
        };
      </script>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=4)
    page._select_exact('Frecuencia de pago', 'MENSUAL', error_code='catalogo')
    assert chrome.execute_script('return window.picks') == 1
    assert chrome.execute_script('return window.saves') == 0
    assert chrome.find_element(By.CSS_SELECTOR, '.ng-value-label').text == 'MENSUAL'


def test_naf_description_fraction_is_normalized_before_save(chrome, tmp_path):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    from test_purchase_order_preload import _draft
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <table><thead><tr><th>No. Artículo</th><th>Descripción</th><th>Cant.</th></tr></thead>
      <tbody><tr><td><input value="CLAVO"></td><td><input id="desc" value="CLAVO 2 ½”"></td><td><input id="qty" value="200"></td></tr></tbody></table>
      <button id="next">Siguiente</button>
    '''))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3)
    draft = _draft()
    draft.articles[0].description = 'CLAVO 2 ½”'
    page._normalize_article_description(draft.articles[0],0)
    assert chrome.find_element(By.ID,'desc').get_attribute('value') == 'CLAVO 2 1/2"'
    assert chrome.find_element(By.ID,'qty').get_attribute('value') == '200'


@pytest.mark.parametrize('attribute', ['readonly', 'disabled'])
def test_naf_readonly_description_updates_form_model_without_enabling_control(chrome, tmp_path, attribute):
    from compras_tn.infrastructure.automation.purchase_orders import GoodsPurchaseOrderPage
    from test_purchase_order_preload import _draft
    chrome.get('data:text/html;charset=utf-8,' + quote('''
      <table><thead><tr><th>No. Artículo</th><th>Descripción</th><th>Cant.</th><th>Precio</th></tr></thead>
      <tbody><tr><td><input id="code" value="10-06-26-288"></td>
      <td><input STATE id="desc" value="CLAVO 2 ½”" oninput="window.order.description=this.value"></td>
      <td><input id="qty" value="200"></td><td><input id="price" value="0.05"></td></tr></tbody></table>
      <script>window.catalog={description:'CLAVO 2 ½”'};window.order={description:window.catalog.description};</script>
    '''.replace('STATE', attribute)))
    page = GoodsPurchaseOrderPage(chrome, tmp_path, element_timeout=3)
    draft = _draft()
    draft.articles[0].description = 'CLAVO 2 ½”'
    page._normalize_article_description(draft.articles[0],0)
    field = chrome.find_element(By.ID,'desc')
    assert field.get_attribute('value') == 'CLAVO 2 1/2"'
    assert field.get_attribute(attribute)
    assert field.is_enabled() == (attribute != 'disabled')
    assert chrome.execute_script('return window.order.description') == 'CLAVO 2 1/2"'
    assert chrome.execute_script('return window.catalog.description') == 'CLAVO 2 ½”'
    assert chrome.find_element(By.ID,'code').get_attribute('value') == '10-06-26-288'
    assert chrome.find_element(By.ID,'qty').get_attribute('value') == '200'
    assert chrome.find_element(By.ID,'price').get_attribute('value') == '0.05'
    assert draft.articles[0].description == 'CLAVO 2 ½”'
