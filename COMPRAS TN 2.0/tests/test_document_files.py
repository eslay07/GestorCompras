from pathlib import Path

import pytest

from compras_tn.application.workflows import WorkflowEngine, WorkflowExecutionError
from compras_tn.domain.models import FlowStep, SessionCredentials, TaskRecord, WorkflowDefinition
from compras_tn.infrastructure.automation.telcos import (
    SeleniumActionExecutor,
    SeleniumTelcosGateway,
)
from compras_tn.infrastructure.document_files import (
    DocumentFileResolver,
    FolderChoiceRequired,
    add_type,
    file_types,
    matches_type,
)


class Settings:
    def __init__(self, root):
        self.values = {("automation", "actua_tareas_carpeta_base"): str(root)}

    def get(self, namespace, key, default=None):
        return self.values.get((namespace, key), default)

    def set(self, namespace, key, value):
        self.values[namespace, key] = value


def flow(types):
    return WorkflowDefinition(name="Adjuntos", steps=[
        FlowStep(action_id="abrir_tareas_personales"),
        FlowStep(action_id="abrir_subida_archivo"),
        FlowStep(action_id="seleccionar_archivo", params={"modo_archivo": "tipos", "tipos_archivo": types}),
        FlowStep(action_id="subir_archivo"),
    ])


@pytest.fixture
def documents(tmp_path):
    root = tmp_path / "general"
    folder = root / "Octubre" / "164404714 - Proyecto"
    folder.mkdir(parents=True)
    (folder / "COTIZACIÓN - UNO.pdf").write_bytes(b"cotizacion uno")
    (folder / "cotizacion - UNO - anterior.xlsx").write_bytes(b"cotizacion anterior")
    (folder / "OC - 373627.pdf").write_bytes(b"orden")
    (folder / "ficha TECNICA.docx").write_bytes(b"ficha")
    return root, folder, Settings(root)


@pytest.mark.parametrize("types,count", [(["cotizacion"], 2), (["orden"], 1), (["cotizacion", "orden"], 3), (["ficha_tecnica"], 1)])
def test_types_include_all_versions_and_formats(documents, types, count):
    root, folder, settings = documents
    wrong = root / "1644047140 - Otra tarea"
    wrong.mkdir()
    (wrong / "COTIZACION.pdf").write_bytes(b"incorrecta")
    manifest = DocumentFileResolver(settings).prepare(flow(types), TaskRecord(task_number="164404714"))["3"]
    assert manifest["folder"] == str(folder.resolve())
    assert len(manifest["files"]) == count
    assert all(Path(item["path"]).parent == folder for item in manifest["files"])


def test_short_keywords_do_not_match_doc_or_cotizacion():
    order = file_types(Settings(Path(".")))[1]
    assert not matches_type(Path("documento.pdf"), order)
    assert not matches_type(Path("cotizacion.pdf"), order)
    assert matches_type(Path("OC-123.pdf"), order)


def test_custom_type_is_persisted_with_stable_id(documents):
    _, folder, settings = documents
    definition = add_type(settings, "Certificado", "certificado, garantía")
    (folder / "GARANTIA.png").write_bytes(b"garantia")
    stored = file_types(settings)[-1]
    assert stored["id"] == definition["id"]
    stored["name"] = "Certificado actualizado"
    result = DocumentFileResolver(settings).prepare(flow([stored["id"]]), TaskRecord(task_number="164404714"))
    assert len(result["3"]["files"]) == 1


def test_duplicate_folders_require_explicit_choice(documents):
    root, folder, settings = documents
    (root / "Septiembre" / folder.name).mkdir(parents=True)
    resolver = DocumentFileResolver(settings)
    with pytest.raises(FolderChoiceRequired) as error:
        resolver.prepare(flow(["cotizacion"]), TaskRecord(task_number="164404714"))
    assert len(error.value.candidates) == 2
    task = TaskRecord(task_number="164404714", payload={"document_folder_choices": {"3": str(folder)}})
    assert resolver.prepare(flow(["cotizacion"]), task)["3"]["folder"] == str(folder)


@pytest.mark.parametrize("problem", ["missing", "empty", "partial"])
def test_no_step_runs_when_required_file_is_invalid(documents, problem):
    _, folder, settings = documents
    order = folder / "OC - 373627.pdf"
    order.unlink()
    if problem == "empty":
        order.write_bytes(b"")
    if problem == "partial":
        (folder / "ORDEN.pdf.crdownload").write_bytes(b"incompleto")
    class Page:
        calls = 0
        def open_personal(self):
            self.calls += 1
    page = Page()
    engine = WorkflowEngine(SeleniumActionExecutor(page, settings, object()))
    with pytest.raises((ValueError, FileNotFoundError)):
        engine.execute(flow(["orden"]), TaskRecord(task_number="164404714"))
    assert page.calls == 0


def test_changed_and_disappeared_manifest_is_rejected(documents):
    _, _, settings = documents
    resolver = DocumentFileResolver(settings)
    task = TaskRecord(task_number="164404714")
    manifest = resolver.prepare(flow(["orden"]), task)
    task.payload["document_file_manifests"] = manifest
    selected = Path(manifest["3"]["files"][0]["path"])
    selected.write_bytes(b"contenido diferente")
    with pytest.raises(ValueError, match="cambió"):
        resolver.prepare(flow(["orden"]), task)
    selected.unlink()
    with pytest.raises(ValueError, match="no existe"):
        resolver.prepare(flow(["orden"]), task)


def test_invalid_tasks_do_not_start_browser(documents, app_paths):
    _, folder, settings = documents
    (folder / "OC - 373627.pdf").unlink()
    class Factory:
        def create(self, *_args):
            raise AssertionError("No debe iniciarse el navegador")
    gateway = SeleniumTelcosGateway(settings, object(), app_paths, Factory())
    result = gateway.execute_workflow(SessionCredentials(username="TEST", email="test@example.com", password="memory"), flow(["orden"]), [TaskRecord(task_number="164404714")], headless=True)
    assert len(result.items) == 1
    assert "No se inició" in result.items[0].message


def test_partial_upload_reports_progress_and_blocks_retry(documents):
    _, _, settings = documents
    manifest = DocumentFileResolver(settings).prepare(flow(["cotizacion"]), TaskRecord(task_number="164404714"))["3"]
    class Page:
        uploaded = 0
        def close_confirmation(self): pass
        def open_upload(self): pass
        def select_file(self, *_args): pass
        def upload(self, _context):
            self.uploaded += 1
            if self.uploaded == 2:
                raise TimeoutError("Sin confirmación")
    context = {"typed_upload_manifest": manifest, "typed_upload_files": manifest["files"], "remote_file_hashes": set()}
    executor = SeleniumActionExecutor(Page(), settings, object())
    with pytest.raises(TimeoutError):
        executor.action_subir_archivo({}, context)
    assert context["document_upload_results"][0]["status"] == "Carga confirmada por Telcos"
    assert "pendiente" in context["document_upload_results"][1]["status"]
    error = WorkflowExecutionError(4, "subir_archivo", TimeoutError("Sin confirmación"), context=context)
    assert SeleniumTelcosGateway._has_irreversible_progress(error)
    with pytest.raises(RuntimeError, match="No se reenviará"):
        executor.action_subir_archivo({}, context)
    assert executor.page.uploaded == 2


@pytest.mark.parametrize("other_files", [("cotizacion.pdf",), ("cotizacion.pdf", "orden.docx"), tuple(f"cotizacion - {index}.pdf" for index in range(5))])
def test_each_task_runs_workflow_once_and_only_uploads_loop(documents, other_files):
    from collections import Counter
    root, _, settings = documents
    other = root / "Octubre/166573896 - Segundo proyecto"
    other.mkdir()
    for name in other_files:
        (other / name).write_bytes(('otro documento ' + name).encode())
    class Page:
        current_task = ""
        calls = []
        CONFIRMATIONS = ()
        long_timeout = 1
        def wait(self, predicate, *args): return predicate(None)
        def wait_idle(self): pass
        def find_now(self, *args): return False
        def open_personal(self): self.calls.append(("open", self.current_task))
        def enter_task(self, number, context):
            self.current_task = number
            self.calls.append(("enter", number))
        def consult(self, number): self.calls.append(("consult", number))
        def _task_row(self): return True
        def row_value(self, row, names): return "PAUSADA"
        def resume(self): self.calls.append(("resume", self.current_task))
        def enter_observation(self, text): self.calls.append(("observation", self.current_task))
        def accept_observation(self): self.calls.append(("accept", self.current_task))
        def close_confirmation(self): self.calls.append(("close", self.current_task))
        def open_upload(self): self.calls.append(("open_upload", self.current_task))
        def remote_file_hashes(self): return set()
        def select_file(self, path, context): context["archivo_seleccionado"] = str(path)
        def upload(self, context): self.calls.append(("upload", self.current_task, context["archivo_seleccionado"]))
    page = Page()
    executor = SeleniumActionExecutor(page, settings, object())
    # Browser stability is covered by the real Chrome tests; this fake measures
    # one workflow per task and multiple uploads within that workflow.
    executor.wait_ready = lambda: None
    workflow = flow(["cotizacion", "orden"])
    workflow.steps[1:1] = [
        FlowStep(action_id="ingresar_numero_tarea"), FlowStep(action_id="consultar"),
        FlowStep(action_id="reanudar_tarea"), FlowStep(action_id="ingresar_observacion", params={"texto": "Una observación"}),
        FlowStep(action_id="aceptar_observacion"), FlowStep(action_id="cerrar_mensaje_ok"),
    ]
    for number, count in (("164404714", 3), ("166573896", len(other_files))):
        context = WorkflowEngine(executor).execute(workflow, TaskRecord(task_number=number))
        # An accidental second upload step must not send confirmed files again.
        executor.action_subir_archivo({}, context)
        uploads = [call for call in page.calls if call[0] == "upload" and call[1] == number]
        assert len(uploads) == count
        assert len({call[2] for call in uploads}) == count
        assert all(Path(call[2]).parent.name.startswith(number + " - ") for call in uploads)
        counters = Counter(call[0] for call in page.calls if call[1] == number)
        for action in ("resume", "observation", "accept"):
            assert counters[action] == 1
        assert counters['enter'] == counters['consult'] == 2  # Read-only precheck + flow.


def test_file_input_replaces_previous_selection_instead_of_accumulating(tmp_path):
    from compras_tn.infrastructure.automation.telcos import TasksPage
    class Field:
        files = []
        def clear(self): self.files = []
        def send_keys(self, path): self.files.append(path)
        def get_attribute(self, name): return self.files[0] if self.files else ""
    field = Field()
    from types import SimpleNamespace
    page = object.__new__(TasksPage)
    page.driver = SimpleNamespace(execute_script=lambda script, target: target.clear())
    page.find = lambda *args, **kwargs: field
    page.find_now = lambda *args, **kwargs: field
    page.wait = lambda condition, *args: condition(None)
    context = {}
    page.select_file(tmp_path / "cotizacion.pdf", context)
    page.select_file(tmp_path / "orden.pdf", context)
    assert field.files == [str((tmp_path / "orden.pdf").resolve())]
    assert context["archivos_seleccionados"] == field.files


def test_batch_validation_continues_valid_tasks_and_reports_missing_type(documents):
    from compras_tn.application.services import ApplicationFacade
    _, _, settings = documents
    facade = object.__new__(ApplicationFacade)
    facade.settings = settings
    rows = facade.prepare_workflow_files(flow(["orden"]), [TaskRecord(task_number="164404714"), TaskRecord(task_number="199999999")])
    assert not rows[0]["error"]
    assert rows[0]["task"].payload["document_file_manifests"]["3"]["files"]
    assert rows[1]["error"]


def test_nested_folder_of_another_task_is_not_selected(documents):
    _, folder, settings = documents
    nested = folder / "199999999 - Otro proyecto"
    nested.mkdir()
    (nested / "COTIZACION - incorrecta.pdf").write_bytes(b"incorrecta")
    manifest = DocumentFileResolver(settings).prepare(flow(["cotizacion"]), TaskRecord(task_number="164404714"))["3"]
    assert len(manifest["files"]) == 2


def test_step_dialog_roundtrip_types_and_legacy_alias(qtbot, documents):
    from types import SimpleNamespace

    from compras_tn.application.workflows import ACTION_REGISTRY
    from compras_tn.presentation.document_widgets import FileSelectionWidget
    from compras_tn.presentation.workflows_page import StepDialog
    _, _, settings = documents
    services = SimpleNamespace(get_setting=settings.get, document_types=lambda: file_types(settings))
    dialog = StepDialog(ACTION_REGISTRY["seleccionar_archivo"], parent=None, services=services)
    qtbot.addWidget(dialog)
    widget = dialog.inputs["ruta"]
    assert isinstance(widget, FileSelectionWidget)
    widget.path.setText("@mi_alias")
    assert dialog.value().params == {"ruta": "@mi_alias"}
    widget.mode.setCurrentIndex(1)
    widget.checks["orden"].setChecked(True)
    value = dialog.value()
    assert value.params["tipos_archivo"] == ["cotizacion", "orden"]
    assert value.params["tipos_nombres"] == ["Cotización", "Orden"]
    restored = StepDialog(ACTION_REGISTRY["seleccionar_archivo"], value, services=services)
    qtbot.addWidget(restored)
    assert restored.value() == value


def test_generated_type_prefix_is_searchable_even_with_different_keywords(documents):
    _, folder, settings = documents
    custom = add_type(settings, "Certificado", "garantia")
    (folder / "CERTIFICADO - CEFEIND.pdf").write_bytes(b"documento")
    manifest = DocumentFileResolver(settings).prepare(flow([custom["id"]]), TaskRecord(task_number="164404714"))
    assert len(manifest["3"]["files"]) == 1


@pytest.mark.parametrize("mode", ["tipos", "alias", "incluido"])
def test_save_workflow_defers_task_specific_file_validation(repositories, tmp_path, mode):
    from compras_tn.application.services import ApplicationFacade
    facade = object.__new__(ApplicationFacade)
    facade.settings = repositories
    facade.catalogs = repositories
    workflow = flow(["cotizacion", "ficha_tecnica"])
    if mode == "alias":
        workflow.steps[2].params = {"ruta": "@archivo_tarea"}
    elif mode == "incluido":
        workflow.steps = [FlowStep(action_id="ejecutar_flujo", params={"nombre": "Adjuntos", "pasos": [step.model_dump() for step in workflow.steps]})]
    saved = facade.save_workflow(workflow)
    assert saved.id is not None
    assert repositories.list_workflows()[0].steps == workflow.steps


@pytest.mark.parametrize("params", [{"ruta": "@sin_configurar"}, {"ruta": "Z:/archivo-inexistente.pdf"}, {"modo_archivo": "tipos", "tipos_archivo": []}, {"modo_archivo": "tipos", "tipos_archivo": ["tipo_desconocido"]}])
def test_save_workflow_still_rejects_invalid_document_configuration(repositories, params):
    from compras_tn.application.services import ApplicationFacade
    facade = object.__new__(ApplicationFacade)
    facade.settings = repositories
    facade.catalogs = repositories
    workflow = flow(["cotizacion"])
    workflow.steps[2].params = params
    with pytest.raises(ValueError):
        facade.save_workflow(workflow)
    assert repositories.list_workflows() == []


def test_multiple_types_allow_one_missing_and_revalidate_manifest(documents):
    _, folder, settings = documents
    (folder / "OC - 373627.pdf").unlink()
    workflow = flow(["cotizacion", "orden"])
    resolver = DocumentFileResolver(settings)
    task = TaskRecord(task_number="164404714")
    manifests = resolver.prepare(workflow, task)
    files = manifests["3"]["files"]
    assert len(files) == 2 and all("cotizacion" in item["types"] for item in files)
    prepared = task.model_copy(update={"payload": {"document_file_manifests": manifests}})
    assert resolver.prepare(workflow, prepared) == manifests

@pytest.mark.parametrize('same_content', [False, True])
def test_existing_telcos_content_is_not_reuploaded(tmp_path, same_content):
    import hashlib
    file = tmp_path/'ORDEN.pdf'
    file.write_bytes(b'contenido nuevo')
    class Page:
        uploaded=0
        closed=0
        def upload(self, context): self.uploaded+=1
        def close_upload_without_saving(self): self.closed+=1
        def close_confirmation(self): raise AssertionError('No server message for omitted upload')
    page=Page()
    remote = hashlib.sha256(b'contenido nuevo' if same_content else b'contenido diferente').hexdigest()
    context={'archivo_seleccionado':str(file), 'remote_file_hashes':{remote}, 'numero_tarea':'163826137'}
    executor=SeleniumActionExecutor(page, object(), object())
    executor.action_subir_archivo({}, context)
    assert page.uploaded == (0 if same_content else 1)
    assert page.closed == (1 if same_content else 0)
    if same_content:
        executor.action_cerrar_mensaje_ok({}, context)
        assert 'Omitido' in context['document_upload_results'][0]['status']
    else:
        assert context['document_upload_results'][0]['status']=='Carga confirmada por Telcos'


def test_duplicate_check_fails_before_any_task_side_effect():
    calls=[]
    class Page:
        def open_personal(self): calls.append('open')
        def enter_task(self, number, context): calls.append('enter')
        def consult(self, number): calls.append('consult')
        def remote_file_hashes(self):
            calls.append('check')
            raise RuntimeError('No se puede leer lista')
        def resume(self): pytest.fail('Never resume before verification')
    executor=SeleniumActionExecutor(Page(), object(), object())
    workflow=WorkflowDefinition(name='Carga',steps=[FlowStep(action_id='reanudar_tarea'), FlowStep(action_id='subir_archivo')])
    with pytest.raises(RuntimeError, match='leer lista'):
        executor.preflight(workflow, {'task_number':'163826137'})
    assert calls == ['open','enter','consult','check']
