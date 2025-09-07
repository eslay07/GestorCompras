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
        pop_port = os.getenv('POP_PORT', self.data.get('pop_port', 995))
        try:
            self.data['pop_port'] = int(pop_port)
        except (TypeError, ValueError):
            self.data['pop_port'] = 995
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
        self.data.setdefault('seafile_repo_id', 'c0de837d-2c58-4f58-802d-aa513aaad8b2')
        self.data.setdefault('seafile_subfolder', '/prueba')
        self.data.setdefault('correo_reporte', 'jotoapanta@telconet.ec')
        self.data.setdefault('remitente_adicional', 'naf@telconet.ec')
        self.data.setdefault('compra_bienes', False)
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


