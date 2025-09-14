import pytest

try:
    import tkinter as tk
    from gestorcompras.gui.html_editor import HtmlEditor
except Exception:  # pragma: no cover - tkinter may be missing
    tk = None


def test_get_html_wraps_bullet_lines():
    if tk is None:
        pytest.skip("tkinter not available")
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk display not available")
    editor = HtmlEditor(root)
    editor.text.insert("1.0", "\u2022 item uno\nnormal")
    editor.text.tag_add("list", "1.0", "1.end")
    html = editor.get_html()
    root.destroy()
    assert "text-indent:-15px" in html
    assert "normal" in html
