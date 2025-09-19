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
        # override credentials with environment variables if present
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

        # default values when config file is empty
        self.data.setdefault('pop_server', 'pop.telconet.ec')
        self.data.setdefault('pop_port', 995)
        self.data.setdefault('usuario', 'jotoapanta@telconet.ec')
        self.data.setdefault('carpeta_destino_local', r'E:\Seadrive\jotoapan_1\Shared with me\BD_TELCO\BIENES')
        self.data.setdefault('carpeta_analizar', r'E:\Seadrive\jotoapan_1\Shared with me\BD_TELCO\BIENES')
        self.data.setdefault('seafile_url', 'https://telcodrive.telconet.net')
        self.data.setdefault('seafile_repo_id', 'ede837d2-5de8-45f8-802d-aa513aaad8b2')
        self.data.setdefault('seafile_subfolder', '/prueba')
        self.data.setdefault('correo_reporte', 'jotoapanta@telconet.ec')
        self.data.setdefault('remitente_adicional', 'naf@telconet.ec')
        self.data.setdefault('smtp_server', 'smtp.telconet.ec')
        self.data.setdefault('smtp_port', 587)
        self.data.setdefault('smtp_ssl_port', 465)
        self.data.setdefault('smtp_plain_port', 25)
        self.data.setdefault('smtp_usuario', self.data.get('usuario'))
        self.data.setdefault('smtp_password', self.data.get('password'))
        self.data.setdefault('compra_bienes', False)
        self.data.setdefault('headless', False)
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
        # persist values so configuration survives between executions
        self.save()
        return self

    def save(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)

    # convenience property accessors
    def __getattr__(self, item):
        return self.data.get(item)

    # validations
    def validate(self):
        repo_id = self.data.get('seafile_repo_id', '')
        try:
            uuid.UUID(repo_id)
        except Exception as exc:
            raise ValueError("seafile_repo_id invalido") from exc
        sub = (self.data.get('seafile_subfolder', '/') or '/').strip()
        if not sub.startswith('/'):
            sub = '/' + sub
        self.data['seafile_subfolder'] = sub
        if not self.data.get('pop_server'):
            raise ValueError('pop_server requerido')
        if not self.data.get('pop_port'):
            raise ValueError('pop_port requerido')
        return True


