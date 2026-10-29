from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

import pytest

from compras_tn.domain.models import SessionCredentials, Supplier
from compras_tn.infrastructure.document_files import file_types
from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
from compras_tn.infrastructure.quotations import LOCAL_ZONE, QuotationOrganizer

TASK = "164404714"


class Sheets:
    def __init__(self):
        self.catalog = {TASK: {"project": "DERRROCAMIENTO DE BAÑO", "error": "", "items": []}, "165381630": {"project": "MUEBLES", "error": "", "items": []}}
    def read_task_catalog(self):
        return self.catalog


class Mailbox:
    messages = []
    def __init__(self, *_args, **_kwargs): pass
    def user(self, _value): pass
    def pass_(self, _value): pass
    def uidl(self):
        return b"OK", [f"{i} uid-{i}".encode() for i in range(1, len(self.messages)+1)], 0
    def top(self, i, _lines):
        return b"OK", self.messages[i-1].split(b"\r\n\r\n", 1)[0].split(b"\r\n"), 0
    def retr(self, i):
        return b"OK", self.messages[i-1].split(b"\r\n"), 0
    def quit(self): pass


def message(subject=f"Re: SOLICITUD DE COTIZACION {TASK}", sender="Ventas <ventas@cefeind-ecu.com>", old=False):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["Message-ID"] = subject, sender, "<test@local>"
    received = datetime.now(LOCAL_ZONE) - timedelta(days=100 if old else 0)
    msg["Date"] = format_datetime(received)
    msg.set_content("Adjunto la oferta solicitada")
    msg.add_attachment(b"cotizacion", maintype="application", subtype="pdf", filename="Proforma No 2355.pdf")
    msg.add_attachment(b"ficha", maintype="application", subtype="octet-stream", filename="Ficha tecnica.xlsx")
    msg.add_attachment(b"plano", maintype="application", subtype="octet-stream", filename="Plano.dwg")
    msg.add_attachment(b"logo", maintype="image", subtype="png", filename="logo.png", disposition="inline")
    return msg.as_bytes(policy=msg.policy.clone(linesep="\r\n"))


@pytest.fixture
def organizer(database, repositories, app_paths, tmp_path):
    root = tmp_path / "BD_TN"
    (root / "Octubre").mkdir(parents=True)
    repositories.set("quotations", "root", str(root))
    repositories.save(Supplier(name="CEFEIND", ruc="0012345678901", email_primary="ventas@cefeind-ecu.com"))
    sheets = Sheets()
    value = QuotationOrganizer(database, repositories, repositories, sheets, app_paths, Mailbox)
    # Use today's real local month for scan/save, and preserve casing.
    month = value.month_dir()
    month.mkdir(exist_ok=True)
    return value


def scan(organizer, manual=False):
    now = datetime.now(LOCAL_ZONE)
    return organizer.scan(SessionCredentials(username="TEST", email="test@example.com", password="memory"), now-timedelta(days=7), now+timedelta(seconds=1), [TASK] if manual else None)


def test_scan_report_includes_extra_formats_but_does_not_create_task_folders(organizer):
    Mailbox.messages = [message()]
    rows = scan(organizer)
    assert len(rows) == 3
    assert {r["type_id"] for r in rows} == {"cotizacion", "ficha_tecnica", "otros"}
    assert {r["supplier"] for r in rows} == {"CEFEIND"}
    assert all(Path(r["cached_path"]).is_file() for r in rows)
    assert not any(p.name.startswith(TASK) for p in organizer.root().rglob("*"))


def test_unknown_sender_excluded_and_registered_manual_search_includes_old_processed(organizer):
    Mailbox.messages = [message(sender="Nuevo <nuevo@example.com>", old=True), message(old=True)]
    assert scan(organizer) == []
    rows = scan(organizer, True)
    assert len(rows) == 3
    assert {row["supplier"] for row in rows} == {"CEFEIND"}
    organizer.save([rows[0]])
    assert any(row["status"] == "Ya guardado" for row in scan(organizer, True))


def test_versions_no_overwrite_identical_omit_and_missing_file_restore(organizer):
    Mailbox.messages = [message()]
    row = scan(organizer)[0]
    saved = organizer.save([row])[0]
    original = Path(saved["saved_path"])
    identical = organizer.save([row])[0]
    assert identical["status"] == "Ya guardado"
    assert Path(identical["saved_path"]) == original
    # Another distinct attachment from the same supplier creates a version.
    from compras_tn.infrastructure.document_files import inspect_file
    new_cache = organizer.cache / "new-version"
    new_cache.write_bytes(b"version nueva")
    new = dict(row, identity="another-identity", cached_path=str(new_cache), sha256=inspect_file(new_cache)["sha256"])
    other = organizer.save([new])[0]
    assert other["status"] == "Guardado"
    assert other["saved_path"] != str(original)
    assert original.read_bytes() == b"cotizacion"
    original.unlink()
    restored = organizer.save([saved])[0]
    assert Path(restored["saved_path"]).read_bytes() == b"cotizacion"


def test_unknown_task_and_ambiguous_subject_need_review(organizer):
    Mailbox.messages = [message(subject="SOLICITUD DE COTIZACION 199999999"), message(subject=f"SOLICITUD DE COTIZACION {TASK} y 165381630")]
    rows = scan(organizer)
    assert all(r["error"] for r in rows)
    with pytest.raises(ValueError):
        organizer.prepare_save(rows)
    row = next(r for r in rows if r.get("ambiguous_subject"))
    row = dict(row, task_number=TASK, ambiguous_subject=False)
    assert not organizer.prepare_save([row])[0]["error"]


def test_duplicate_destinations_require_selection_and_reuse_existing_month(organizer):
    Mailbox.messages = [message()]
    month = organizer.month_dir()
    (month / (TASK + " - PRIMERA")).mkdir()
    second = month / (TASK + " - SEGUNDA")
    second.mkdir()
    rows = scan(organizer)
    row = rows[0]
    assert len(row["folder_candidates"]) == 2
    with pytest.raises(ValueError, match="Elija una carpeta"):
        organizer.prepare_save([row])
    row["chosen_folder"] = str(second)
    assert organizer.prepare_save([row])[0]["planned_folder"] == str(second)
    assert organizer.month_dir(datetime(2026, 10, 13, tzinfo=LOCAL_ZONE)).name == "Octubre"


def test_source_change_and_destination_change_are_blocked(organizer):
    Mailbox.messages = [message()]
    row = scan(organizer)[0]
    organizer.sheets.catalog[TASK]["project"] = "OTRO PROYECTO"
    with pytest.raises(ValueError, match="destino cambió"):
        organizer.prepare_save([row])
    organizer.sheets.catalog[TASK]["project"] = "DERRROCAMIENTO DE BAÑO"
    Path(row["cached_path"]).write_bytes(b"corrupto")
    with pytest.raises(ValueError, match="cambió"):
        organizer.prepare_save([row])


def test_general_catalog_reads_blocks_before_oc_start_and_includes_existing_orders():
    def row(code, desc, project):
        return [code, desc, "1", "Proveedor", "10", "373627", "", "", "", "", project]
    catalog = GoogleSheetsGateway.parse_task_catalog([
        row("", TASK, "PROYECTO"), row("ITEM", "Producto", "PROYECTO"),
        row("", "165381630", "MUEBLES"), row("OTRO", "Mesa", "MUEBLES"),
    ])
    assert catalog[TASK]["project"] == "PROYECTO"
    assert catalog[TASK]["items"][0]["code"] == "ITEM"
    conflict = GoogleSheetsGateway.parse_task_catalog([row("", TASK, "UNO"), row("ITEM", "Producto", "DOS")])
    assert "contradictorias" in conflict[TASK]["error"]


def test_save_selected_attachments_has_exact_preview_and_unique_batch_names(organizer):
    Mailbox.messages = [message()]
    rows = scan(organizer)
    first = rows[0]
    second = dict(rows[1], type_id="cotizacion")
    prepared = organizer.prepare_save([first, second])
    assert prepared[0]["planned_path"] != prepared[1]["planned_path"]
    saved = organizer.save(prepared)
    assert all(r["status"] == "Guardado" for r in saved)
    assert [r["saved_path"] for r in saved] == [r["planned_path"] for r in prepared]
    assert saved[1]["saved_path"].endswith(".xlsx")


def test_interrupted_publish_does_not_leave_partial_document_and_can_resume(organizer, monkeypatch):
    import os
    Mailbox.messages = [message()]
    row = scan(organizer)[0]
    real_rename = os.rename
    def failed_publish(*_args, **_kwargs):
        raise OSError("Publicación interrumpida")
    monkeypatch.setattr(os, "rename", failed_publish)
    failed = organizer.save([row])[0]
    assert failed["status"] == "Error al guardar"
    folder = Path(failed["planned_folder"])
    assert not list(folder.glob("*.pdf"))
    assert not list(folder.glob("*.tmp"))
    monkeypatch.setattr(os, "rename", real_rename)
    retried = organizer.save([failed])[0]
    assert retried["status"] == "Guardado"
    assert Path(retried["saved_path"]).read_bytes() == b"cotizacion"


def test_supplier_secondary_email_matches_and_missing_sender_name_uses_localpart(organizer):
    supplier = organizer.suppliers.list()[0]
    supplier.email_secondary = "alternate@example.com"
    organizer.suppliers.save(supplier)
    Mailbox.messages = [message(sender="alternate@example.com"), message(sender="unknown@example.com")]
    rows = scan(organizer)
    assert {r["supplier"] for r in rows} == {"CEFEIND"}


def test_no_automatic_save_before_user_confirmation_in_ui(qtbot, organizer, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import QObject, Signal

    from compras_tn.presentation.quotations_page import QuotationsPage
    class Jobs(QObject):
        job_finished = Signal(str, object)
        job_failed = Signal(str, str)
        job_progress = Signal(str, int, int, str)
        submitted = []
        def state(self, _identifier): return "succeeded"
        def submit(self, *_args):
            self.submitted.append(_args)
            return "job"
    jobs = Jobs()
    services = SimpleNamespace(get_setting=organizer.settings.get, document_types=lambda: file_types(organizer.settings))
    page = QuotationsPage(services, jobs)
    qtbot.addWidget(page)
    Mailbox.messages = [message()]
    page.scan_job = "scan"
    rows = scan(organizer)
    page.finished("scan", rows)
    assert len(jobs.submitted) == 0
    page.prepare_job = "prepare"
    from PySide6.QtWidgets import QDialog

    from compras_tn.presentation.widgets import ReviewDialog
    monkeypatch.setattr(ReviewDialog, "exec", lambda *_args: QDialog.Rejected)
    page.finished("prepare", organizer.prepare_save([rows[0]]))
    assert len(jobs.submitted) == 0
    assert not any(p.name.startswith(TASK) for p in organizer.root().rglob("*"))


@pytest.mark.parametrize("subject,accepted", [
    (f"RE: SOLICTUD DE COTIZACON {TASK}", True),
    (f"FW: solicitud de cotización ({TASK})", True),
    (f"Cotizacion {TASK}", False),
    (f"CAMBIO DE LLANTAS {TASK}", False),
    ("SOLICITUD DE COTIZACION", False),
])
def test_subject_filter_typo_tolerance(subject, accepted):
    from compras_tn.infrastructure.quotations import quotation_subject
    assert quotation_subject(subject) == accepted


def test_repeated_scan_reuses_headers_and_attachment_cache(organizer, monkeypatch):
    Mailbox.messages = [message(), message(sender="internal@telconet.ec")]
    rows = scan(organizer)
    assert len(rows) == 3
    def forbidden(*args):
        raise AssertionError("No debe solicitar cabeceras ni adjuntos conocidos")
    monkeypatch.setattr(Mailbox, "top", forbidden)
    monkeypatch.setattr(Mailbox, "retr", forbidden)
    assert len(scan(organizer, True)) == 3


def test_imap_search_filters_on_server_and_reads_without_marking_seen():
    from compras_tn.infrastructure.quotation_mail import QuotationIMAP
    class IMAP:
        def __init__(self, *args, **kwargs): self.calls = []
        def login(self, *args): pass
        def select(self, name, readonly=False):
            assert readonly and name == "INBOX"
            return "OK", []
        def response(self, name): return name, [b"17"]
        def uid(self, command, *args):
            self.calls.append((command, args))
            if command == "SEARCH":
                return "OK", [b"9 2"]
            return "OK", [(b"header", b"Subject: SOLICITUD DE COTIZACION 164404714\r\nFrom: ventas@example.com")]
        def logout(self): pass
    now = datetime.now(LOCAL_ZONE)
    mailbox = QuotationIMAP("host", 993, ["ventas@example.com", "alternate@example.com"], now-timedelta(days=7), now, [], IMAP)
    mailbox.user("me@example.com")
    mailbox.pass_("memory")
    _, lines, _ = mailbox.uidl()
    assert len(lines) == 2
    criteria = mailbox.connection.calls[0][1][-1]
    assert 'FROM "ventas@example.com"' in criteria and "SINCE" in criteria and "BEFORE" in criteria
    mailbox.top(1, 0)
    mailbox.retr(1)
    assert all("BODY.PEEK" in call[1][-1] for call in mailbox.connection.calls if call[0] == "FETCH")
    mailbox.tasks = [TASK]
    mailbox.uidl()
    assert 'SUBJECT "' + TASK + '"' in mailbox.connection.calls[-1][1][-1]
    assert "SINCE" not in mailbox.connection.calls[-1][1][-1]


def test_settings_groups_keep_shared_connections_in_general():
    from compras_tn.presentation.settings_page import SETTINGS, setting_group
    lookup = {(spec.namespace, spec.key): setting_group(spec) for spec in SETTINGS}
    assert lookup["downloads", "pop_server"] == "General"
    assert lookup["email", "imap_server"] == "General"
    assert lookup["quotations", "root"] == "Organizador de archivos"
    assert lookup["automation", "actua_timeout"] == "Orquestador Telcos"


def test_manual_search_does_not_hide_second_valid_task_in_subject(organizer):
    Mailbox.messages = [message(subject=f"SOLICITUD DE COTIZACION {TASK} y 165381630")]
    rows = scan(organizer, True)
    assert rows and all(row["ambiguous_subject"] and row["error"] for row in rows)
    assert set(rows[0]["task_candidates"]) == {TASK, "165381630"}


def test_absent_general_tasks_are_hidden_from_scan_and_history(organizer):
    Mailbox.messages = [message(subject="SOLICITUD DE COTIZACION 199999999"), message()]
    rows = scan(organizer)
    assert len(rows) == 3 and {row["task_number"] for row in rows} == {TASK}
    organizer.sheets.catalog.pop(TASK)
    assert scan(organizer, True) == []


def test_missing_month_and_task_folder_are_created_only_when_saving(organizer):
    month = organizer.month_dir()
    month.rmdir()
    Mailbox.messages = [message()]
    row = scan(organizer)[0]
    assert not month.exists()
    planned = organizer.prepare_save([row])[0]
    assert Path(planned["planned_folder"]).parent == month
    assert not month.exists()
    saved = organizer.save([planned])[0]
    assert saved["status"] == "Guardado"
    assert Path(saved["saved_path"]).is_file()
    assert Path(saved["saved_path"]).parent.parent == month


def test_review_dialog_has_scrollable_table_and_visible_buttons(qtbot):
    from PySide6.QtWidgets import QDialogButtonBox

    from compras_tn.presentation.widgets import ReviewDialog
    dialog = ReviewDialog("Archivos", "Revise antes de guardar", ["Tarea", "Destino"], [(TASK, "C:/" + "x" * 200)] * 150, "Guardar archivos")
    qtbot.addWidget(dialog)
    dialog.resize(950, 560)
    dialog.show()
    qtbot.wait(20)
    accept = dialog.buttons.button(QDialogButtonBox.Ok)
    cancel = dialog.buttons.button(QDialogButtonBox.Cancel)
    assert dialog.table.verticalScrollBar().maximum() > 0
    assert dialog.rect().contains(accept.mapTo(dialog, accept.rect().bottomRight()))
    assert dialog.rect().contains(cancel.mapTo(dialog, cancel.rect().bottomRight()))
    assert accept.isVisible() and cancel.isVisible()


def test_organizer_select_all_and_clear_preserve_other_columns(organizer, qtbot):
    from types import SimpleNamespace

    from PySide6.QtCore import Qt

    from compras_tn.presentation.jobs import JobManager
    from compras_tn.presentation.quotations_page import QuotationsPage
    services = SimpleNamespace(get_setting=organizer.settings.get, document_types=lambda: file_types(organizer.settings))
    page = QuotationsPage(services, JobManager())
    qtbot.addWidget(page)
    Mailbox.messages = [message()]
    page.rows = scan(organizer)
    page.render()
    page.resize(1100, 720)
    page.show()
    qtbot.wait(20)
    page.set_all_selected(False)
    assert not page.selected_rows()
    page.set_all_selected(True)
    assert len(page.selected_rows()) == 3
    assert all(page.table.item(index, 0).checkState() == Qt.Checked for index in range(3))
    assert page.table.height() >= 180
    assert not page.panel.log.isVisible()


def test_local_multiple_files_create_missing_month_and_project_folder(organizer, tmp_path):
    month = organizer.month_dir()
    month.rmdir()
    source = tmp_path / 'local'
    source.mkdir()
    first = source / f'{TASK} CEFEIND proforma.pdf'
    second = source / f'{TASK} CEFEIND ficha tecnica.xlsx'
    first.write_bytes(b'oferta local')
    second.write_bytes(b'ficha local')
    rows = organizer.scan_local([str(first), str(second), str(first)])
    assert len(rows) == 2
    assert not month.exists()
    assert {r['task_number'] for r in rows} == {TASK}
    assert {r['supplier'] for r in rows} == {'CEFEIND'}
    assert {r['type_id'] for r in rows} == {'cotizacion', 'ficha_tecnica'}
    prepared = organizer.prepare_save(rows)
    assert not month.exists()
    saved = organizer.save(prepared)
    folder = month / (TASK + ' - DERRROCAMIENTO DE BAÑO')
    assert folder.is_dir()
    assert all(Path(r['saved_path']).parent == folder for r in saved)
    assert {p.read_bytes() for p in folder.iterdir()} == {b'oferta local', b'ficha local'}
    assert first.read_bytes() == b'oferta local'
    assert second.read_bytes() == b'ficha local'
    assert all(r['status'] == 'Ya guardado' for r in organizer.save(prepared))


def test_local_unknown_and_ambiguous_tasks_require_selection(organizer, tmp_path):
    unknown = tmp_path / 'CEFEIND proforma.pdf'
    ambiguous = tmp_path / f'{TASK} 165381630 CEFEIND proforma.pdf'
    unknown.write_bytes(b'unknown')
    ambiguous.write_bytes(b'ambiguous')
    rows = organizer.scan_local([str(unknown), str(ambiguous)])
    assert all(r['ambiguous_subject'] and r['error'] for r in rows)
    assert TASK in rows[0]['task_candidates']
    with pytest.raises(ValueError, match='Seleccione la tarea'):
        organizer.prepare_save(rows)
    reviewed = dict(rows[0], task_number=TASK, ambiguous_subject=False)
    assert organizer.prepare_save([reviewed])[0]['project'] == 'DERRROCAMIENTO DE BAÑO'


def test_local_source_change_is_blocked_and_missing_file_is_reported(organizer, tmp_path):
    path = tmp_path / f'{TASK} CEFEIND proforma.pdf'
    path.write_bytes(b'original')
    row = organizer.scan_local([str(path)])[0]
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='cambió'):
        organizer.prepare_save([row])
    path.unlink()
    result = organizer.scan_local([str(path)])
    assert result[0]['error']


def test_organizer_dates_reset_to_today_when_opened(qtbot, repositories, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate
    from compras_tn.presentation.quotations_page import QuotationsPage
    from compras_tn.presentation.jobs import JobManager
    from test_application_services import _facade
    facade, *_ = _facade(repositories, tmp_path)
    jobs = JobManager()
    page = QuotationsPage(facade, jobs)
    qtbot.addWidget(page)
    today = datetime.now(LOCAL_ZONE).date()
    assert page.start.date().toPython() == today
    assert page.end.date().toPython() == today
    page.start.setDate(QDate(2020, 1, 1))
    page.end.setDate(QDate(2020, 1, 2))
    page.show()
    assert page.start.date().toPython() == today
    assert page.end.date().toPython() == today
    calls = []
    monkeypatch.setattr('compras_tn.presentation.quotations_page.QFileDialog.getOpenFileNames',
        lambda *_: (['one.pdf', 'two.xlsx'], ''))
    monkeypatch.setattr(jobs, 'submit', lambda kind, callback: calls.append(callback) or 'local-test')
    monkeypatch.setattr(facade, 'scan_local_quotations', lambda paths, *_: paths)
    page.choose_local_files()
    assert calls[0](None, None) == ['one.pdf', 'two.xlsx']


def test_local_pdf_supplier_ruc_excludes_telconet_even_if_registered(organizer, tmp_path):
    from test_october15_changes import pdf
    organizer.suppliers.save(Supplier(name='TELCONET', ruc='0991327371001'))
    path = pdf(tmp_path / f'{TASK} proforma.pdf',
        'CLIENTE TELCONET RUC 0991327371001 PROVEEDOR RUC 0012345678901')
    row = organizer.scan_local([str(path)])[0]
    assert row['supplier'] == 'CEFEIND'
    assert row['supplier_ruc'] == '0012345678901'
    assert row['detected_rucs'] == ['0012345678901']
    assert not row['error']


def test_local_ruc_content_overrides_wrong_filename_and_ambiguous_needs_review(organizer, tmp_path):
    from test_october15_changes import pdf
    organizer.suppliers.save(Supplier(name='OTRO', ruc='1791234567001'))
    path = pdf(tmp_path / f'{TASK} CEFEIND proforma.pdf', 'RUC 1791234567001 CLIENTE 0991327371001')
    assert organizer.scan_local([str(path)])[0]['supplier'] == 'OTRO'
    pdf(path, 'RUC 1791234567001 RUC 0012345678901 CLIENTE 0991327371001')
    row = organizer.scan_local([str(path)])[0]
    assert row['supplier'] == ''
    assert row['error']
    assert set(row['supplier_candidates']) == {'CEFEIND', 'OTRO'}


def test_local_unregistered_ruc_and_customer_only_do_not_assign_supplier(organizer, tmp_path):
    from test_october15_changes import pdf
    organizer.suppliers.save(Supplier(name='TELCONET', ruc='0991327371001'))
    path = pdf(tmp_path / f'{TASK} CEFEIND proforma.pdf', 'RUC 1791234567001 CLIENTE 0991327371001')
    row = organizer.scan_local([str(path)])[0]
    assert not row['supplier']
    assert 'RUC no registrado' in row['status']
    pdf(path, 'CLIENTE TELCONET RUC 0991327371001')
    assert not organizer.scan_local([str(path)])[0]['supplier']


def test_local_excel_ruc_and_manual_task_refresh(organizer, tmp_path):
    from openpyxl import Workbook
    path = tmp_path / 'proforma.xlsx'
    workbook = Workbook()
    workbook.active.append(['Cliente', '0991327371001', 'Proveedor', '0012345678901'])
    workbook.save(path)
    workbook.close()
    row = organizer.scan_local([str(path)])[0]
    assert row['supplier'] == 'CEFEIND'
    reviewed = organizer.review_local_task(dict(row, task_number=TASK))
    assert reviewed['project'] == organizer.sheets.catalog[TASK]['project']
    assert Path(reviewed['planned_folder']).name == TASK + ' - ' + reviewed['project']
    assert not reviewed['error']
    changed = organizer.review_local_task(dict(reviewed, task_number='165381630'))
    assert Path(changed['planned_folder']).name == '165381630 - MUEBLES'
    missing = organizer.review_local_task(dict(reviewed, task_number='199999999'))
    assert missing['error'] == 'La tarea no existe en GENERAL.'
    assert missing['project'] == missing['planned_folder'] == ''


def test_local_manual_task_updates_table_project_and_destination(qtbot, organizer, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLineEdit
    from compras_tn.presentation.quotations_page import QuotationsPage
    from compras_tn.presentation.jobs import JobManager
    path = tmp_path / 'CEFEIND proforma.txt'
    path.write_text('RUC 0012345678901', encoding='utf-8')
    services = SimpleNamespace(get_setting=organizer.settings.get, set_setting=organizer.settings.set,
        document_types=lambda: file_types(organizer.settings),
        review_local_quotation_tasks=organizer.review_local_tasks)
    jobs = JobManager()
    page = QuotationsPage(services, jobs)
    qtbot.addWidget(page)
    page.rows = organizer.scan_local([str(path)])
    page.render()
    editor = page.table.cellWidget(0, 1)
    assert isinstance(editor, QLineEdit)
    editor.setText(TASK)
    callbacks = []
    monkeypatch.setattr(jobs, 'submit', lambda kind, callback: callbacks.append(callback) or 'task-review')
    monkeypatch.setattr(jobs, 'state', lambda job: 'succeeded')
    page.review_local_tasks()
    result = callbacks[0](None, None)
    page.finished('task-review', result)
    assert page.table.item(0, 6).text() == 'DERRROCAMIENTO DE BAÑO'
    assert Path(page.table.item(0, 7).text()).name == TASK + ' - DERRROCAMIENTO DE BAÑO'
    assert page.reviewed_row(0)['task_number'] == TASK


def test_local_batch_reads_general_once_for_all_manual_tasks(organizer, tmp_path, monkeypatch):
    paths = [tmp_path / 'proforma uno.txt', tmp_path / 'proforma dos.txt']
    for path in paths:
        path.write_text('RUC 0012345678901 CLIENTE 0991327371001', encoding='utf-8')
    rows = organizer.scan_local([str(path) for path in paths])
    rows[0]['task_number'] = TASK
    rows[1]['task_number'] = '165381630'
    calls = []
    catalog = organizer.sheets.catalog
    monkeypatch.setattr(organizer.sheets, 'read_task_catalog', lambda: calls.append('read') or catalog)
    reviewed = organizer.review_local_tasks(rows)
    assert calls == ['read']
    assert [r['project'] for r in reviewed] == ['DERRROCAMIENTO DE BAÑO', 'MUEBLES']
    assert all(r['supplier'] == 'CEFEIND' and not r['error'] for r in reviewed)
    assert Path(reviewed[0]['planned_folder']).name.startswith(TASK)
    assert Path(reviewed[1]['planned_folder']).name.startswith('165381630')
