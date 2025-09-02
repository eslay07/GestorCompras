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


