import pytest

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from gestorcompras.gui.html_editor import HtmlEditor
except Exception:  # pragma: no cover - tkinter may be missing
    tk = None
    tkfont = None


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


def test_editor_normalizes_conflicting_font_sizes():
    if tk is None:
        pytest.skip("tkinter not available")
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk display not available")
    editor = HtmlEditor(root)
    editor.set_html('<span style="font-size:11px">abc</span>')
    editor.current_size = "16"
    editor.text.mark_set("insert", "1.1")
    editor.text.insert("insert", "Z")
    editor._apply_active_tags()
    editor._update_current_styles()
    html = editor.get_html()
    tags = editor.text.tag_names("1.1")
    root.destroy()
    assert "size_16" not in tags
    assert "font-size:16px" not in html
    assert "font-size:11px" in html
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw


def test_editor_removes_stale_size_tags_on_type():
    if tk is None:
        pytest.skip("tkinter not available")
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk display not available")
    editor = HtmlEditor(root)
    editor.set_html('<span style="font-size:11px">a</span>')
    editor.text.tag_configure("size_8", font=tkfont.Font(size=8))
    editor.text.tag_add("size_8", "1.0", "1.1")
    editor.text.mark_set("insert", "1.1")
    editor.current_size = "11"
    editor.text.insert("insert", "X")
    editor._apply_active_tags()
    editor._update_current_styles()
    tags = [t for t in editor.text.tag_names("1.1") if t.startswith("size_")]
    html = editor.get_html()
    root.destroy()
    assert tags == ["size_11"]
    assert "font-size:8px" not in html
#=======
#>>>>>>> master
