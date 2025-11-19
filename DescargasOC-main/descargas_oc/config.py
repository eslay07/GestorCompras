import json
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


def _default_path() -> str:
    data_dir = BASE_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    return os.getenv('CONFIG_PATH', str(data_dir / 'config.json'))


class Config:
    def __init__(self, path: str | None = None):
        self.path = path or _default_path()
        self.data: dict = {}
        self.load()

    def load(self):
        load_dotenv()
        try:
            with open(self.path, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}
        # sobrescribe credenciales con variables de entorno cuando existan
        self.data['usuario'] = os.getenv('USUARIO_OC', self.data.get('usuario'))
        self.data['password'] = os.getenv('PASSWORD_OC', self.data.get('password'))
        self.data['pop_server'] = os.getenv('POP_SERVER', self.data.get('pop_server'))
        self.data['remitente_adicional'] = os.getenv(
            'REMITENTE_ADICIONAL', self.data.get('remitente_adicional')
        )

        def _parse_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def _parse_bool(value, default):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "t", "yes", "si", "sí"}:
                    return True
                if lowered in {"0", "false", "f", "no"}:
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            return default

        self.data['pop_port'] = _parse_int(
            os.getenv('POP_PORT', self.data.get('pop_port', 995)), 995
        )
        self.data['smtp_server'] = os.getenv(
            'SMTP_SERVER', self.data.get('smtp_server', 'smtp.telconet.ec')
        )
        self.data['smtp_port'] = _parse_int(
            os.getenv('SMTP_PORT', self.data.get('smtp_port', 587)), 587
        )
        self.data['smtp_ssl_port'] = _parse_int(
            os.getenv('SMTP_SSL_PORT', self.data.get('smtp_ssl_port', 465)), 465
        )
        self.data['smtp_plain_port'] = _parse_int(
            os.getenv('SMTP_PLAIN_PORT', self.data.get('smtp_plain_port', 25)), 25
        )
        self.data['smtp_usuario'] = os.getenv(
            'SMTP_USER',
            self.data.get('smtp_usuario', self.data.get('usuario')),
        )
        self.data['smtp_password'] = os.getenv(
            'SMTP_PASSWORD',
            self.data.get('smtp_password', self.data.get('password')),
        )
        headless_raw = os.getenv('HEADLESS', self.data.get('headless'))
        headless_val = _parse_bool(headless_raw, False)
        self.data['headless'] = headless_val

        abas_headless_raw = os.getenv(
            'ABASTECIMIENTO_HEADLESS',
            self.data.get('abastecimiento_headless', headless_val),
        )
        self.data['abastecimiento_headless'] = _parse_bool(
            abas_headless_raw,
            headless_val,
        )
        self.data.setdefault('max_threads', 5)
        self.data.setdefault('batch_size', 50)

        interval = os.getenv('SCAN_INTERVAL', self.data.get('scan_interval'))
        try:
            val = int(interval) if interval else 300
        except (TypeError, ValueError):
            val = 300
        if val < 300:
            val = 300
        self.data['scan_interval'] = val

        # valores predeterminados cuando el archivo de configuración está vacío
        self.data.setdefault('pop_server', 'pop.telconet.ec')
        self.data.setdefault('pop_port', 995)
        self.data.setdefault('usuario', '')
        self.data.setdefault('carpeta_destino_local', '')
        self.data.setdefault('carpeta_analizar', '')
        self.data.setdefault('correo_reporte', '')
        self.data.setdefault('remitente_adicional', 'naf@telconet.ec')
        self.data.setdefault('smtp_server', 'smtp.telconet.ec')
        self.data.setdefault('smtp_port', 587)
        self.data.setdefault('smtp_ssl_port', 465)
        self.data.setdefault('smtp_plain_port', 25)
        self.data.setdefault('smtp_usuario', self.data.get('usuario'))
        self.data.setdefault('smtp_password', self.data.get('password'))
        self.data.setdefault('compra_bienes', False)
        self.data.setdefault('headless', False)
        self.data.setdefault('abastecimiento_mover_archivos', False)
        self.data.setdefault('abastecimiento_headless', self.data['headless'])
        self.data.setdefault(
            'abastecimiento_carpeta_descarga', self.data.get('carpeta_destino_local')
        )
        self.data.setdefault(
            'abastecimiento_correo_reporte', self.data.get('correo_reporte')
        )
        self.data.setdefault('abastecimiento_solicitantes', [])
        self.data.setdefault('abastecimiento_autorizadores', [])

        def _normalize_list(key: str) -> None:
            raw = self.data.get(key)
            normalized: list[str] = []
            if raw is None:
                pass
            elif isinstance(raw, str):
                normalized = [part.strip() for part in raw.split(',') if part.strip()]
            else:
                try:
                    iterable = list(raw)
                except TypeError:
                    iterable = [raw]
                for item in iterable:
                    text = str(item).strip()
                    if text:
                        normalized.append(text)
            self.data[key] = normalized

        _normalize_list('abastecimiento_solicitantes')
        _normalize_list('abastecimiento_autorizadores')
        # guarda los valores para conservar la configuración entre ejecuciones
        self.save()
        return self

    def save(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)

    # accesores de conveniencia para las propiedades
    def __getattr__(self, item):
        return self.data.get(item)

    # validaciones
    def validate(self):
        if not self.data.get('pop_server'):
            raise ValueError('pop_server requerido')
        if not self.data.get('pop_port'):
            raise ValueError('pop_port requerido')
        return True


