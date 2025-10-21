import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    # al importarse como parte del paquete principal
    from .logger import get_logger
except ImportError:  # pragma: no cover - compatibilidad con importaciones directas en pruebas
    from logger import get_logger

logger = get_logger(__name__)


class SeafileClient:
    def __init__(self, server_url: str, username: str, password: str, *, session_token: str | None = None, timeout: int = 30):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        if session_token:
            self.session_token = session_token
        else:
            self.session_token = self._login(username, password)

    def _login(self, username: str, password: str) -> str:
        url = f"{self.server_url}/api2/auth-token/"
        resp = self.session.post(url, data={'username': username, 'password': password}, timeout=self.timeout)
        if resp.status_code in (401, 403):
            raise RuntimeError('Credenciales inválidas')
        resp.raise_for_status()
        try:
            token = resp.json().get('token')
        except ValueError as e:
            raise RuntimeError('Respuesta inválida del servidor') from e
        if not token:
            raise RuntimeError('No se recibió token')
        return token

    def _headers(self):
        return {'Authorization': f'Token {self.session_token}'}

    def _get_upload_link(self, repo_id: str, parent_dir: str = '/') -> str:
        uuid_regex = r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$"
        if '/' in repo_id or ':' in repo_id or not re.match(uuid_regex, repo_id, re.IGNORECASE):
            raise ValueError("'seafile_repo_id' debe ser un UUID")
        from urllib.parse import quote
        encoded_dir = quote(parent_dir, safe='/')
        url = f"{self.server_url}/api2/repos/{repo_id}/upload-link/?p={encoded_dir}"
        resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code == 404:
            raise RuntimeError('Repositorio no encontrado (404)')
        resp.raise_for_status()
        return resp.text.strip('"')

    def upload_file(self, repo_id: str, file_path: str, parent_dir: str = '/') -> str:
        logger.info("Subiendo %s a %s/%s", file_path, repo_id, parent_dir)
        link = self._get_upload_link(repo_id, parent_dir)
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'parent_dir': parent_dir}
            resp = self.session.post(link, files=files, data=data, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            if not resp.text:
                raise RuntimeError('Respuesta vacía de Seafile')
            return resp.text

