"""Generate real UI captures using an isolated, synthetic demonstration database."""
import os,sys,tempfile,re,json
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'COMPRAS TN 2.0/src'))
from PySide6.QtWidgets import QApplication,QLabel,QLineEdit,QPlainTextEdit,QTableWidget,QTableWidgetItem,QTabWidget,QDateEdit,QAbstractItemView
from PySide6.QtCore import QDate,Qt
from compras_tn.bootstrap import build_container
from compras_tn.paths import AppPaths
from compras_tn.presentation.main_window import MainWindow
from compras_tn.presentation.theme import STYLE
from compras_tn.presentation.workflows_page import WorkflowEditor
from compras_tn.domain.models import FlowStep
app=QApplication([])
from PySide6.QtGui import QFontDatabase, QFont
for font_file in ['segoeui.ttf','segoeuib.ttf','segoeuii.ttf']:
    font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font_file)
    assert font_id>=0, 'No se pudo cargar Segoe UI'
app.setFont(QFont('Segoe UI',10))
app.setStyleSheet(STYLE)
output=repo/'docs/capturas';output.mkdir(parents=True,exist_ok=True)
records=[]
def slug(s):
    import unicodedata
    return re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()).strip('-')
def neutral(s):
    if '@' in s:s=re.sub(r'[\w.+%\-]+@[\w.\-]+','CORREO OCULTO',s)
    s=s.replace('smtp.telconet.ec','servidor-configurable').replace('telcodrive.telconet.net','servicio.example.invalid').replace('telconet.ec','dominio-corporativo')
    if str(Path.home()) in s or 'ctn-public-demo-' in s:s='Datos activos: carpeta local de demostración'
    return s
with tempfile.TemporaryDirectory(prefix='ctn-public-demo-') as data:
    c=build_container(app_paths=AppPaths.from_root(Path(data)),project_root=repo/'COMPRAS TN 2.0')
    for namespace,key,value in [('quotations','root','C:/DEMO/Documentos'),('downloads','seafile_url','https://servicio.example.invalid'),('email','smtp_server','servidor-configurable')]:c.repositories.set(namespace,key,value)
    w=MainWindow(c);w.resize(1600,1000);w.root_stack.setCurrentWidget(w.shell);w.user_label.setText('USUARIO DE DEMOSTRACIÓN')
    w.statusBar().showMessage('DATOS DE DEMOSTRACIÓN · Sin conexión a correo ni portales · Datos sensibles ocultos')
    for label in w.findChildren(QLabel):label.setText(neutral(label.text()))
    for field in w.findChildren(QLineEdit):
        field.setText(neutral(field.text()));field.setPlaceholderText(neutral(field.placeholderText()))
    for date in w.findChildren(QDateEdit):date.setDate(QDate(2026,10,28))
    for edit in w.findChildren(QPlainTextEdit):
        if 'OC manual' in edit.placeholderText():edit.setPlainText('900001\n900002')
        elif 'tarea' in edit.placeholderText().lower():edit.setPlainText('900000001\n900000002')
    for editor in w.findChildren(WorkflowEditor):
        editor.name.setText('Flujo de demostración')
        editor.steps=[FlowStep(action_id='abrir_tareas_personales'),FlowStep(action_id='ingresar_numero_tarea'),FlowStep(action_id='consultar'),FlowStep(action_id='seleccionar_tarea'),FlowStep(action_id='reanudar_tarea'),FlowStep(action_id='ingresar_observacion',params={'texto':'Validación de demostración'}),FlowStep(action_id='aceptar_observacion'),FlowStep(action_id='cerrar_mensaje_ok')]
        editor.render()
    for label in w.findChildren(QLabel):
        if label.text().startswith('0 órdenes detectadas:'):
            label.setText('Demostración de revisión: 2 órdenes de ejemplo; identidades ocultas. No se ha ejecutado ninguna carga.')
    for table in w.findChildren(QTableWidget):
        if table.rowCount()>0:continue
        headers=[table.horizontalHeaderItem(i).text() if table.horizontalHeaderItem(i) else '' for i in range(table.columnCount())]
        if not headers:continue
        table.setRowCount(2)
        for r in range(2):
            for col,h in enumerate(headers):
                h=h.lower()
                value='—'
                if any(k in h for k in ['correo','destinatario','remitente','proveedor','ruc','responsable','empleado','solicitante','sobrenombre']):value='[OCULTO]'
                elif 'tarea' in h:value=str(900000001+r)
                elif h.strip() in ['oc','orden','n° oc']:value=str(900001+r)
                elif 'estado' in h:value=['Lista para revisar','Pendiente'][r]
                elif 'resultado' in h:value=['Validación correcta','Revisión requerida'][r]
                elif 'archivo' in h or 'pdf' in h:value=f'documento_demo_{r+1}.pdf'
                elif 'fecha' in h:value='28/10/2026'
                elif 'departamento' in h:value='ÁREA DEMO'
                elif 'nombre' in h:value='Registro de demostración'
                elif 'cantidad' in h or 'artículo' in h:value='2'
                elif 'total' in h:value='$ 100.00'
                elif 'asunto' in h:value='Solicitud de demostración'
                elif h=='id':value=str(r+1)
                elif 'paso' in h:value=str(r+1)
                elif 'destino' in h or 'carpeta' in h:value='C:/DEMO/Documentos'
                item=QTableWidgetItem(value)
                if any(k in h for k in ['cargar','procesar','enviar','guardar']):item.setText('');item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked)
                table.setItem(r,col,item)
        table.resizeColumnsToContents()
    # Replace the only reference image containing an actual task number with a safe native control.
    from PySide6.QtWidgets import QWidget,QVBoxLayout
    reference=QWidget();layout=QVBoxLayout(reference)
    layout.addWidget(QLabel('Número tarea:'));layout.addWidget(QLineEdit('[OCULTO]'))
    reference.resize(420,80);reference.show();app.processEvents()
    reference.grab().save(str(repo/'COMPRAS TN 2.0/src/compras_tn/presentation/assets/telcos/numero_tarea.jpg'))
    reference.close()
    w.show();app.processEvents()
    def save(name,caption):
        app.processEvents();file=slug(name)+'.png';w.grab().save(str(output/file));records.append({'file':file,'caption':caption})
    w.root_stack.setCurrentWidget(w.login);w.login.username.setPlaceholderText('Usuario corporativo');save('00-acceso','Acceso y sesión');w.root_stack.setCurrentWidget(w.shell)
    names=['01-inicio','02-correos-bienes','03-organizador-archivos','04-carga-oc-automatica','05-seguimientos','06-reasignacion-bienes','07-descargas-bienes','08-orquestador-bienes','09-correos-servicios','10-reasignacion-servicios','11-descargas-servicios','12-orquestador-servicios','13-configuracion']
    for i,name in enumerate(names):
        w._navigate(i,w.nav_buttons[i]);save(name,w.nav_buttons[i].text())
        page=w.pages.widget(i)
        tabs=page.findChildren(QTabWidget)
        # Capture each first-level module tab; this includes the new transfer queue and editors.
        if tabs and i in [6,7,10,11,12]:
            tab=tabs[0]
            for j in range(1,tab.count()):
                tab.setCurrentIndex(j);save(name+'-'+slug(tab.tabText(j)),w.nav_buttons[i].text()+' · '+tab.tabText(j))
            tab.setCurrentIndex(0)
    w.close();c.database.close()
(output/'manifest.json').write_text(json.dumps({'synthetic':True,'real_services_accessed':False,'captures':records},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Capturas de interfaz generadas: {len(records)}; sin correo, proveedores ni servicios reales')