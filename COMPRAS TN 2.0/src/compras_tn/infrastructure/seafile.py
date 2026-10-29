from __future__ import annotations

import hashlib
import re
import threading
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from compras_tn.application.ports import SettingsRepository
from compras_tn.domain.models import SessionCredentials


class SeafileHttpGateway:
    def __init__(self, settings: SettingsRepository):
        self.settings = settings
        self._local = threading.local()
        self.delivery: Any = None

    @contextmanager
    def batch(self):
        with ExitStack() as stack:
            self._local.stack = stack
            self._local.remotes = {}
            try:
                yield
            finally:
                self._local.stack = None
                self._local.remotes = {}

    def validate(self, credentials: SessionCredentials) -> None:
        repo = str(self.settings.get('downloads', 'seafile_repo_id', '')).strip()
        if repo:
            with self.connection(credentials, repo) as remote:
                remote.list_dir(str(self.settings.get('downloads', 'seafile_parent_dir', '/BD_TN')))
            return
        session = self._session()
        try:
            self._token(credentials, session)
        finally:
            self._close_session(session)

    @contextmanager
    def connection(self, credentials, repo_id):
        stack = getattr(self._local, 'stack', None)
        if stack is not None:
            key = (credentials.email, repo_id)
            if key not in self._local.remotes:
                self._local.remotes[key] = stack.enter_context(self._connection(credentials, repo_id))
            yield self._local.remotes[key]
        else:
            with self._connection(credentials, repo_id) as remote:
                yield remote

    @contextmanager
    def _connection(self, credentials, repo_id):
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', repo_id):
            raise ValueError('Configure el UUID de Mi Biblioteca en Descargas.')
        session = self._session()
        try:
            token = self._token(credentials, session)
            remote = SeafileRemote(session, self._base_url(), token, repo_id)
            response = session.get(f'{remote.base}/api2/repos/', headers=remote.headers, timeout=30)
            response.raise_for_status()
            library = next((item for item in response.json() if item.get('id') == repo_id), None)
            if library is None or library.get('permission') != 'rw':
                raise PermissionError('La biblioteca no existe o no permite escritura para esta cuenta.')
            yield remote
        finally:
            self._close_session(session)

    def upload(
        self,
        credentials: SessionCredentials,
        file_path: Path,
        repo_id: str,
        parent_dir: str = "/",
    ) -> str:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"No se encontró el archivo para Seafile: {file_path}")
        if not re.fullmatch(
            r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}",
            repo_id,
            re.IGNORECASE,
        ):
            raise ValueError("El repositorio de Seafile debe ser un UUID válido.")
        session = self._session()
        try:
            token = self._token(credentials, session)
            base = self._base_url()
            headers = {"Authorization": f"Token {token}"}
            link_response = session.get(
                f"{base}/api2/repos/{repo_id}/upload-link/?p={quote(parent_dir, safe='/')}",
                headers=headers,
                timeout=30,
            )
            link_response.raise_for_status()
            upload_link = str(link_response.text).strip().strip('"')
            parsed_link = urlsplit(upload_link)
            if parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
                raise RuntimeError("Seafile devolvió un enlace de carga inválido.")
            with file_path.open("rb") as source:
                response = session.post(
                    upload_link,
                    headers=headers,
                    data={"parent_dir": parent_dir},
                    files={"file": source},
                    timeout=60,
                )
            response.raise_for_status()
            return response.text
        finally:
            self._close_session(session)

    def _token(
        self,
        credentials: SessionCredentials,
        session: requests.Session | None = None,
    ) -> str:
        client = session or self._session()
        response = client.post(
            f"{self._base_url()}/api2/auth-token/",
            data={"username": credentials.email, "password": credentials.password},
            timeout=30,
        )
        if response.status_code in {401, 403}:
            raise PermissionError("Seafile rechazó las credenciales de sesión.")
        response.raise_for_status()
        try:
            token = str(response.json().get("token") or "")
        except ValueError as exc:
            raise RuntimeError("Seafile devolvió una respuesta inválida.") from exc
        if not token:
            raise RuntimeError("Seafile no devolvió un token de sesión.")
        return token

    def _base_url(self) -> str:
        value = str(self.settings.get("downloads", "seafile_url", "")).rstrip("/")
        if not value:
            raise ValueError("La URL de Seafile no está configurada.")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La URL de Seafile no es válida.")
        return value

    @staticmethod
    def _session() -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _close_session(session: object) -> None:
        close = getattr(session, "close", None)
        if callable(close):
            close()


class SeafileRemote:
    def __init__(self, session, base, token, repo):
        self.session, self.base, self.repo = session, base, repo
        self.headers = {'Authorization': f'Token {token}'}
        self.cache = {}

    def request(self, method, suffix, **kwargs):
        response = self.session.request(method, f'{self.base}/api2/repos/{self.repo}/{suffix}',
                                        headers=self.headers, timeout=30, **kwargs)
        response.raise_for_status()
        return response

    def list_dir(self, path):
        if path not in self.cache:
            self.cache[path] = self.request('GET', 'dir/', params={'p': path}).json()
        return self.cache[path]

    def ensure_dir(self, path):
        parent = str(PurePosixPath(path).parent)
        name = PurePosixPath(path).name
        if any(item['name'] == name and item.get('type') == 'dir' for item in self.list_dir(parent)):
            return
        try:
            self.request('POST', 'dir/', params={'p': path}, data={'operation': 'mkdir'})
        except requests.HTTPError:
            self.cache.pop(parent, None)
            if not any(item['name'] == name and item.get('type') == 'dir' for item in self.list_dir(parent)):
                raise
        self.cache.pop(parent, None)

    def content_hash(self, path):
        link = self.request('GET', 'file/', params={'p': path}).json()
        self.check_link(link)
        # Signed file links do not need the authentication token.
        with self.session.get(link, timeout=60, stream=True) as response:
            response.raise_for_status()
            digest = hashlib.sha256()
            for chunk in response.iter_content(1024 * 1024):
                digest.update(chunk)
            return digest.hexdigest()

    def check_link(self, link):
        parsed = urlsplit(str(link))
        if parsed.scheme != 'https' or parsed.netloc != urlsplit(self.base).netloc:
            raise ValueError('El enlace Seafile no pertenece al servidor HTTPS configurado.')

    def upload_verified(self, path, parent):
        from compras_tn.infrastructure.delivery import fingerprint
        expected = fingerprint(path)
        remote_path = str(PurePosixPath(parent) / path.name)
        self.cache.pop(parent, None)
        exists = any(item['name'] == path.name for item in self.list_dir(parent))
        if exists:
            if self.content_hash(remote_path) == expected:
                return 'identical'
            raise ValueError('Conflicto: existe un archivo del mismo nombre con contenido diferente.')
        link = self.request('GET', 'upload-link/', params={'p': parent}).json()
        self.check_link(link)
        try:
            with path.open('rb') as source:
                response = self.session.post(link, params={'ret-json': '1'}, data={'parent_dir': parent, 'replace': '0'},
                                             files={'file': source}, timeout=60)
            response.raise_for_status()
            uploaded = response.json()
            if not isinstance(uploaded, list) or len(uploaded) != 1 or uploaded[0].get('name') != path.name:
                raise ValueError('Seafile cambió el nombre durante la carga; revise posibles cargas concurrentes.')
        except requests.RequestException:
            # A timeout may happen after the server committed the upload.
            self.cache.pop(parent, None)
            if self.content_hash(remote_path) != expected:
                raise
            return 'uploaded'
        if self.content_hash(remote_path) != expected:
            raise ValueError('La carga terminó sin coincidencia de contenido; requiere revisión.')
        return 'uploaded'
