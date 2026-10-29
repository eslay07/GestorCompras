"""Genera las muestras publicables de GestorCompras usando capturas saneadas.

Requiere reportlab y Pillow. Ejecutar desde cualquier directorio.
"""
from pathlib import Path
from html import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs' / 'portafolio'
OUT.mkdir(parents=True, exist_ok=True)
CAP = ROOT / 'docs' / 'capturas'
W, H = 595.28, 841.89
M = 42
NAVY = HexColor('#10283F')
TEAL = HexColor('#007F86')
GRAY = HexColor('#486171')
PALE = HexColor('#EAF3F5')
BASE = 'https://github.com/eslay07/GestorCompras'
FONT = Path('C:/Windows/Fonts')
if (FONT / 'segoeui.ttf').exists():
    pdfmetrics.registerFont(TTFont('Body', str(FONT / 'segoeui.ttf')))
    pdfmetrics.registerFont(TTFont('Strong', str(FONT / 'segoeuib.ttf')))
else:
    FONT = Path('/usr/share/fonts/truetype/dejavu')
    pdfmetrics.registerFont(TTFont('Body', str(FONT / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('Strong', str(FONT / 'DejaVuSans-Bold.ttf')))


class Document:
    def __init__(self, name, title):
        self.c = canvas.Canvas(str(OUT / name), pagesize=(W, H), pageCompression=1)
        self.c.setTitle(title)
        self.c.setAuthor('Jimmy Toapanta')
        self.c.setSubject('GestorCompras - versión pública actual - octubre 2026')
        self.page = 0

    def text(self, text, y, size=10.3, color=GRAY, bold=False, width=W-2*M, x=M):
        style = ParagraphStyle('p', fontName='Strong' if bold else 'Body',
                               fontSize=size, leading=size*1.4, textColor=color)
        p = Paragraph(text, style)
        _, height = p.wrap(width, H)
        if y-height < 51:
            raise ValueError(f'Texto fuera de página {self.page}: {text[:80]}')
        p.drawOn(self.c, x, y-height)
        return y-height

    def start(self, label, title, subtitle=''):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.c.setFillColor(NAVY)
        self.c.rect(0, H-12, W, 12, fill=1, stroke=0)
        self.text('GESTORCOMPRAS  /  '+label.upper(), H-36, 9, TEAL, True)
        y = self.text(title, H-67, 26, NAVY, True)
        if subtitle:
            y = self.text(subtitle, y-11, 11)
        self.c.setStrokeColor(HexColor('#D5E2E7'))
        self.c.line(M, 42, W-M, 42)
        self.c.setFont('Body', 8)
        self.c.setFillColor(GRAY)
        self.c.drawString(M, 27, 'Jimmy Toapanta  |  Actualizado: 29 octubre 2026')
        self.c.drawRightString(W-M, 27, str(self.page))
        return y-20

    def section(self, title, body, y):
        y = self.text(title, y, 12, NAVY, True)
        return self.text(body, y-5)-14

    def image(self, name, y, caption='', width=W-2*M):
        from PIL import Image
        path = CAP / name
        im = Image.open(path)
        height = width * im.height / im.width
        if y-height < 70:
            raise ValueError(f'Imagen fuera de página {self.page}: {name}')
        self.c.drawImage(str(path), M, y-height, width=width, height=height,
                         preserveAspectRatio=True, mask='auto')
        y -= height+8
        if caption:
            y = self.text(caption, y, 8.3)
        return y-15

    def link(self, label, url, y):
        return self.text(f'<link href="{escape(url, quote=True)}" color="#007F86">{escape(label)}</link>', y, 10.5)-9

    def save(self):
        self.c.save()
        print(self.page, 'páginas')


def presentation():
    d = Document('GestorCompras_Presentacion_Actual.pdf', 'GestorCompras | Automatización aplicada a compras')
    y = d.start('Presentación profesional', 'Menos recorridos manuales.<br/>Más capacidad operativa.',
                'Una aplicación de escritorio que conecta correo, documentos, hojas de cálculo y portales de compras.')
    y = d.image('01-inicio.png', y, 'Interfaz actual de PySide6. Captura con datos de demostración.')
    y = d.section('Del problema operativo a una herramienta de software',
        'Mi experiencia en compras me permitió identificar pasos repetidos: preparar correos, localizar documentos, transcribir órdenes y actualizar tareas. GestorCompras reúne esos recorridos en módulos con procesamiento por lotes y ejecución en segundo plano.', y)
    y = d.section('Mi aporte',
        'Análisis del proceso, integración de fuentes y portales, diseño de flujos, validaciones, recuperación de pendientes, pruebas y preparación de un instalador para Windows.', y)
    d.link('Revisar código y documentación', BASE, y)

    y = d.start('Impacto operativo', 'El valor se ve por módulo.',
                'Tiempos aproximados reportados durante el uso. El volumen y la preparación importan.')
    rows = [
        ('Actividad de referencia', 'Manual', 'Con el proyecto'),
        ('10-20 correos de despacho', '20-40 min', '10 s / lote preparado*'),
        ('Organizar 3-4 documentos', '6-7 min', '2 min'),
        ('Cargar 1 OC de 5 ítems', '4-5 min', '2 min'),
        ('Reasignar 5 tareas', '10-15 min', '3 min'),
        ('Descargar y organizar 6 OC', '7-8 min o más', '3 min'),
        ('Seguimiento de 1 tarea', '4-6 min', '1 min'),
    ]
    widths = [222, 111, W-2*M-333]
    for i, row in enumerate(rows):
        rh = 38 if i else 35
        d.c.setFillColor(NAVY if i == 0 else PALE if i%2 else white)
        d.c.rect(M, y-rh, W-2*M, rh, fill=1, stroke=0)
        x = M+8
        for cell, cw in zip(row, widths):
            d.text(escape(cell), y-9, 9, white if i == 0 else NAVY, i == 0, cw-15, x)
            x += cw
        y -= rh
    y = d.text('* El envío de correos parte de un lote preparado. La selección, adjuntos y revisión inicial se contabilizan aparte.', y-12, 8.8)-20
    y = d.section('Escenario mensual: 45 tareas y 80 OC de Bienes',
        'El cálculo publicado estima <b>17-21 horas de recorrido manual frente a unas 6 h 15 min con el proyecto</b>: aproximadamente <b>11-15 horas de ahorro operativo al mes</b>. Incluye correos, documentos, carga, reasignación, descargas y seguimiento, con los volúmenes y supuestos detallados en la documentación.', y)
    y = d.section('Capacidad para asumir más trabajo',
        'La automatización ejecuta los pasos repetitivos mientras el usuario atiende otras actividades. Esa autonomía permite ampliar capacidad; debe medirse la intervención humana y la atención a excepciones antes de convertir el ahorro operativo en una decisión de dotación.', y)
    y = d.text('La cifra mensual es una estimación. No equivale a horas netas de personal ni acredita una reducción de puestos. Servicios sigue en desarrollo y no se cuenta como flujo automatizado.', y, 9.2)-16
    d.link('Consultar tabla mensual, supuestos y proyección', BASE+'/blob/main/docs/IMPACTO_OPERATIVO.md', y)

    y = d.start('Implementación y evidencia', 'Una solución que se puede revisar.',
                'Python · PySide6 · Selenium · Google Sheets · SQLAlchemy · SQLite · Alembic')
    y = d.section('Arquitectura',
        'Interfaz de escritorio → casos de uso y validaciones → adaptadores de correo, hojas, documentos y portales → persistencia local. Las capas separan reglas del negocio, automatización y presentación.', y)
    y = d.section('Seis módulos principales',
        'Correos masivos · Organizador de archivos · Carga automática de OC · Reasignación · Descargas de OC · Orquestador visual. Seguimientos y Configuración completan el recorrido.', y)
    y = d.section('Controles para el trabajo diario',
        'Preparación y revisión de lotes, estados por elemento, control de duplicados según el flujo, recuperación de pendientes y registro de errores. Los procesos pueden continuar en segundo plano.', y)
    y = d.section('Entrega y alcance actual',
        'Instalador público para Windows con dependencias de Python 3.12/3.13. El lanzamiento se comprobó con Python 3.12; para 3.13 se verificó la resolución sin conexión. Las integraciones reales requieren configuración y accesos propios. Bienes es el flujo operativo; Servicios es una base de interfaz en desarrollo.', y)
    y = d.section('Demostración sin información operativa privada',
        'El repositorio incluye 25 capturas con datos de demostración. Los PDF muestran la interfaz real; las filas sintéticas ilustran su uso y no prueban transacciones realizadas al crear las imágenes.', y)
    for label, suffix in [('Guía visual actual en PDF', '/blob/main/docs/portafolio/GestorCompras_Guia_Visual_Actual.pdf'),
                          ('Galería y explicación de todos los módulos', '/blob/main/docs/MODULOS.md'),
                          ('Instalación y arquitectura', '/blob/main/docs/GUIA_TECNICA.md'),
                          ('Instalador completo en Releases', '/releases/tag/v2.0.0')]:
        y = d.link(label, BASE+suffix, y)
    d.link('Jimmy Toapanta | Portafolio', 'https://github.com/eslay07', y)
    d.save()


MODULES = [
    ('Correos masivos', '02-correos-bienes.png',
     'Enviar solicitudes de despacho con asunto, plantilla y orden de compra para cada proveedor.',
     ['Prepare la selección de órdenes y los documentos que corresponden a cada destinatario.',
      'Revise destinatarios, asunto, plantilla y adjuntos antes del envío.',
      'Confirme el lote y revise el resultado de cada mensaje.'],
     '10-20 correos en unos 10 segundos de envío por lote preparado; antes, 2 minutos por correo. La preparación y revisión se miden por separado.'),
    ('Organizador de archivos', '03-organizador-archivos.png',
     'Identificar cotizaciones y guardarlas con el proveedor y la tarea correctos.',
     ['Configure la carpeta central y los datos de identificación de proveedores.',
      'Escanee mensajes con la tarea en el asunto o seleccione archivos locales. En la selección local se usa el RUC para buscar al proveedor.',
      'Revise la asociación tarea-proveedor, la carpeta de destino y la etiqueta antes de guardar.'],
     '3-4 archivos: unos 2 minutos frente a 6-7 minutos manuales.'),
    ('Carga automática de OC', '04-carga-oc-automatica.png',
     'Llevar los datos de Google Sheets al portal de órdenes de compra.',
     ['Configure la hoja y el acceso autorizado al portal.',
      'Prepare el lote y revise proveedor, solicitante, artículos, cantidades y precios.',
      'Ejecute la carga y compruebe en la hoja los números de orden y los datos de autorización registrados.'],
     'Una OC de cinco ítems: unos 2 minutos de ejecución frente a 4-5 manuales. El tiempo depende de los ítems y de la respuesta del portal.'),
    ('Reasignación de tareas', '06-reasignacion-bienes.png',
     'Preparar tareas completas para reasignarlas con su información de cierre.',
     ['Escanee los correos de tareas completas y revise el lote detectado.',
      'Compruebe factura, ingreso, observaciones, departamento y usuario de destino.',
      'Confirme la ejecución y revise el estado de cada tarea en el portal.'],
     'Cinco tareas: unos 3 minutos por lote frente a 10-15 manuales.'),
    ('Descargas de OC', '07-descargas-bienes.png',
     'Descargar, renombrar y organizar órdenes aprobadas por tarea y proveedor.',
     ['Detecte aprobaciones por escaneo de correo o introduzca un lote de números de OC.',
      'Revise la selección y la carpeta o subcarpetas configuradas como destino.',
      'Ejecute el lote y compruebe los documentos descargados y los estados pendientes.'],
     'Seis OC: unos 3 minutos frente a 7-8 minutos o más, incluyendo renombrado y ubicación manual.'),
    ('Orquestador de flujos', '08-orquestador-bienes-editor-visual.png',
     'Construir secuencias reutilizables de seguimiento y archivos para el portal de tareas.',
     ['Prepare o abra una secuencia en el editor visual.',
      'Configure los pasos, observaciones y alias de archivos; revise un caso de prueba.',
      'Seleccione un lote, ejecute el flujo y revise los resultados por tarea.'],
     'Una tarea: alrededor de 1 minuto frente a 4-6 minutos manuales, según los pasos del flujo.'),
]


def guide():
    d = Document('GestorCompras_Guia_Visual_Actual.pdf', 'GestorCompras | Guía visual de módulos e instalación')
    y = d.start('Guía visual', 'Conocer el proyecto.<br/>Preparar el primer lote.',
                'Guía de recorrido de la versión pública actual. Bienes: flujo operativo. Servicios: en desarrollo.')
    y = d.image('01-inicio.png', y, 'Interfaz real con datos de demostración. No contiene el catálogo operativo de proveedores.')
    y = d.section('Antes de usar una integración',
        'Instale el paquete completo de Releases o prepare el entorno desde el código. Registre su configuración de proveedores, rutas, plantillas y asignaciones. Google Sheets, correo y portales necesitan servicios y permisos propios.', y)
    y = d.section('Cómo leer esta guía',
        'Cada página presenta una función, un recorrido de revisión y un tiempo de referencia. Las pantallas muestran datos sintéticos; las acciones reales se ejecutan después de revisar la selección y confirmar en la aplicación.', y)
    d.link('Instalador y guía técnica completa', BASE+'/blob/main/docs/GUIA_TECNICA.md', y)
    for title, image, purpose, steps, timing in MODULES:
        y = d.start('Módulos de Bienes', title, purpose)
        y = d.image(image, y, 'Demostración de interfaz. Proveedores, correos y valores operativos se sustituyeron u ocultaron.')
        for i, step in enumerate(steps, 1):
            y = d.text(f'<b>{i}.</b> '+step, y)-10
        y = d.section('Referencia de tiempo', timing, y-4)
        d.text('Referencia aproximada reportada por el autor. La red, los datos y los pasos del portal pueden cambiar la duración. Revise siempre el resultado del lote.', y, 8.8)
    y = d.start('Configuración y operación', 'Mantener el contexto en un solo lugar.',
                'Proveedores, asignaciones, plantillas y opciones de cada módulo.')
    y = d.image('13-configuracion.png', y, 'Configuración mostrada con identidades ocultas y datos de demostración.')
    y = d.section('Preparación inicial',
        'Registre los proveedores y sus datos de identificación; revise las asignaciones y plantillas. Configure rutas, correo, hoja de cálculo, portales y almacenamiento propios según los módulos que utilizará.', y)
    y = d.section('Trabajo en segundo plano',
        'Prepare el lote, revise los datos y confirme la operación. La automatización puede continuar mientras atiende otras funciones; después compruebe los estados y gestione las excepciones o pendientes.', y)
    y = d.section('Seguimientos y recuperación',
        'Seguimientos complementa la comunicación por selección y plantillas. La cola de subidas de Descargas permite revisar transferencias y recuperar pendientes. El editor del Orquestador conserva flujos reutilizables.', y)
    d.link('Galería completa: editor, alias, colas y configuración', BASE+'/blob/main/docs/MODULOS.md', y)
    y = d.start('Instalación y enlaces', 'Del repositorio al entorno de trabajo.',
                'Windows de 64 bits · Python 3.12 o 3.13 · paquete público 2.0.0')
    y = d.section('Instalador completo',
        'Descargue el paquete de Releases, extraiga todo el contenido y ejecute instalar.py. El instalador requiere un Python compatible ya instalado; selecciona las dependencias correspondientes y verifica el entorno. El perfil público está vacío y debe configurarse con datos propios.', y)
    y = d.section('Inicio desde el código',
        'Cree un entorno virtual en una ruta corta, instale requirements.txt y el paquete editable de COMPRAS TN 2.0, y ejecute run.py desde la raíz. El archivo COMPRAS 3.0.pyw conserva su nombre por compatibilidad; la versión del paquete es 2.0.0. Los comandos completos están en la guía técnica enlazada abajo.', y)
    y = d.section('Estado de validación',
        'El lanzamiento se comprobó con Python 3.12; para 3.13 se verificó la resolución de dependencias sin conexión. Las pruebas de integraciones reales requieren accesos autorizados y no forman parte de la ejecución predeterminada.', y)
    y = d.section('Alcance',
        'Bienes es el flujo actual. Servicios conserva una base de interfaz y no es un recorrido completo. Las capturas y los tiempos de esta guía no validan Servicios ni representan transacciones realizadas al generar las imágenes.', y)
    for label, url in [('Código y presentación del proyecto', BASE),
                       ('Guía técnica y comandos de instalación', BASE+'/blob/main/docs/GUIA_TECNICA.md'),
                       ('Instalador completo', BASE+'/releases/tag/v2.0.0'),
                       ('25 capturas y explicación de módulos', BASE+'/blob/main/docs/MODULOS.md'),
                       ('Impacto mensual y supuestos', BASE+'/blob/main/docs/IMPACTO_OPERATIVO.md'),
                       ('Notificación automática de tareas', 'https://github.com/eslay07/Notificacion-automatica-tareas'),
                       ('Portafolio de Jimmy Toapanta', 'https://github.com/eslay07')]:
        y = d.link(label, url, y)
    d.save()


if __name__ == '__main__':
    presentation()
    guide()
