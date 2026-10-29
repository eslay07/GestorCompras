from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

from compras_tn.domain.models import EmailTemplate

ENVIRONMENT = Environment(
    autoescape=select_autoescape(default_for_string=True),
    undefined=StrictUndefined,
)


class JinjaTemplateRenderer:
    def render(self, template: EmailTemplate, context: dict[str, Any]) -> str:
        html = ENVIRONMENT.from_string(template.html).render(**context)
        signature = Path(template.signature_path) if template.signature_path else None
        if signature and signature.is_file():
            mime = mimetypes.guess_type(signature.name)[0] or "image/png"
            encoded = base64.b64encode(signature.read_bytes()).decode("ascii")
            image = f'<p><img alt="Firma" src="data:{mime};base64,{encoded}"></p>'
            if re.search(r"</body\s*>", html, re.IGNORECASE):
                html = re.sub(r"</body\s*>", lambda _: image + "</body>", html,
                              count=1, flags=re.IGNORECASE)
            else:
                html += image
        return html
