import smtplib
from email.message import EmailMessage

try:  # allow running as script
    from .config import Config
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger

logger = get_logger(__name__)

SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 465


def enviar_reporte(exitosas, faltantes, cfg: Config):
    if not exitosas and not faltantes:
        return
    destinatario = cfg.correo_reporte
    usuario = cfg.usuario
    password = cfg.password
    if not destinatario or not usuario or not password:
        logger.warning('Datos de correo incompletos, no se enviará reporte')
        return
    mensaje = EmailMessage()
    mensaje['Subject'] = 'Reporte de órdenes descargadas'
    mensaje['From'] = usuario
    mensaje['To'] = destinatario
    cuerpo = 'Órdenes subidas correctamente:\n'
    for num in exitosas:
        cuerpo += f'- {num}\n'
    if faltantes:
        cuerpo += '\nNo se encontraron archivos para las siguientes OC:\n'
        for num in faltantes:
            cuerpo += f'- {num}\n'
    mensaje.set_content(cuerpo)
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(usuario, password)
            smtp.send_message(mensaje)
        logger.info('Reporte enviado')
    except Exception as e:
        logger.error('No se pudo enviar reporte: %s', e)

