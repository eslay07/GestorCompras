"""Shared quota budget and bounded, cancellable Sheets HTTP retries."""
from collections import deque
from contextlib import contextmanager
import random
import threading
import time

from gspread.exceptions import APIError
from gspread.http_client import HTTPClient

_context = threading.local()
_lock = threading.Lock()
_windows = {'read': deque(), 'write': deque()}
REQUESTS_PER_MINUTE = 45


def pause(seconds, message):
    progress = getattr(_context, 'progress', None)
    cancelled = getattr(_context, 'cancelled', None)
    if progress:
        progress(0, 0, message)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cancelled and cancelled():
            raise RuntimeError('Espera de Google Sheets cancelada por el usuario.')
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def reserve_request(method, endpoint):
    kind = 'read' if method.lower() == 'get' or 'batchGet' in endpoint else 'write'
    while True:
        with _lock:
            now = time.monotonic()
            window = _windows[kind]
            while window and now - window[0] >= 61:
                window.popleft()
            if len(window) < REQUESTS_PER_MINUTE:
                window.append(now)
                return
            delay = max(0.01, 61 - (now - window[0]))
        pause(delay, f'Google Sheets: esperando {delay:.0f} s para respetar la cuota; el lote continúa después.')


@contextmanager
def sheets_context(progress=None, cancelled=None):
    previous = (getattr(_context, 'progress', None), getattr(_context, 'cancelled', None))
    _context.progress, _context.cancelled = progress, cancelled
    try:
        yield
    finally:
        _context.progress, _context.cancelled = previous


class QuotaHTTPClient(HTTPClient):
    def request(self, method, endpoint, **kwargs):
        for attempt in range(8):
            reserve_request(method, endpoint)
            try:
                return super().request(method, endpoint, **kwargs)
            except APIError as exc:
                status = getattr(exc.response, 'status_code', None)
                if status not in (429, 500, 502, 503, 504) or attempt == 7:
                    if attempt == 7 and status in (429, 500, 502, 503, 504):
                        exc.sheets_retries_exhausted = True
                    raise
                retry_after = getattr(exc.response, 'headers', {}).get('Retry-After', '0')
                try:
                    retry_after = float(retry_after)
                except (TypeError, ValueError):
                    retry_after = 0
                delay = max(retry_after, min(2 ** (attempt + 1), 64) + random.random())
                pause(delay, f'Google Sheets HTTP {status}: esperando {delay:.0f} s; reintento {attempt + 1}/7 sin regenerar la OC.')
