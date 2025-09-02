import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'descargas_oc'))
from config import Config

def test_load_and_env_override(tmp_path, monkeypatch):
    cfg_file = tmp_path / 'config.json'
    data = {
        'usuario': 'user',
        'password': 'pass',
        'seafile_url': 'http://server',
    }
    cfg_file.write_text(json.dumps(data))
    monkeypatch.setenv('USUARIO_OC', 'env_user')
    cfg = Config(path=str(cfg_file))
    assert cfg.usuario == 'env_user'
    assert cfg.seafile_url == 'http://server'


