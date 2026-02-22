import os
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from tkinter import font as tkfont
from html import escape


class _Tooltip:
    """Tooltip simple que aparece al pasar el cursor sobre un widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip,
            text=self._text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=4,
            pady=2,
        ).pack()

    def _hide(self, event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


class HtmlEditor(ttk.Frame):
    """Editor de texto enriquecido con barra descriptiva y selector de firma integrado."""

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._signature_path = ""
        self._create_widgets()
        self._setup_tags()
        self.active_tags: set = set()
        self.default_font = self.font_var.get()
        self.default_size = self.size_var.get()
        self.current_font = self.default_font
        self.current_size = self.default_size
        self.current_color = None
        self.current_bg = None
        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<ButtonRelease-1>", self._update_current_styles)
        self.text.bind("<<Selection>>", self._update_current_styles)
        self.text.bind("<FocusIn>", self._update_current_styles)
        for seq in ("<<Paste>>", "<Control-v>", "<Command-v>"):
            self.text.bind(seq, self._handle_paste)
        self.text.bind("<Control-b>", lambda e: self._make_bold() or "break")
        self.text.bind("<Control-i>", lambda e: self._make_italic() or "break")
        self.text.bind("<Control-u>", lambda e: self._make_underline() or "break")
        self._update_current_styles()

    # ── pequeñas utilidades ───────────────────────────────────────────────────

    def _btn(self, parent, text: str, command, tooltip: str, **kw) -> ttk.Button:
        btn = ttk.Button(parent, text=text, command=command, **kw)
        btn.pack(side="left", padx=1, pady=1)
        _Tooltip(btn, tooltip)
        return btn

    def _sep(self, parent):
        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=3, pady=2)

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    # ── gestión de firma ─────────────────────────────────────────────────────

    def get_signature_path(self) -> str:
        """Retorna la ruta de la imagen de firma configurada."""
        return self._signature_path

    def set_signature_path(self, path: str):
        """Establece la ruta de la imagen de firma y actualiza la etiqueta."""
        self._signature_path = path or ""
        if self._signature_path:
            self._sig_label.config(
                text=os.path.basename(self._signature_path),
                foreground="#000000",
            )
        else:
            self._sig_label.config(text="(ninguna)", foreground="#888888")

    def _select_signature(self):
        path = filedialog.askopenfilename(
            title="Seleccionar imagen de firma",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if path:
            self.set_signature_path(path)
            self._set_status(f"Firma seleccionada: {os.path.basename(path)}")

    def _remove_signature(self):
        self.set_signature_path("")
        self._set_status("Imagen de firma eliminada")

    def _clear_all(self):
        self.text.delete("1.0", "end")
        self._set_status("Contenido del editor borrado")

    # ── construcción de la interfaz ──────────────────────────────────────────

    def _create_widgets(self):
        # ── Fila 1: Formato de texto ──
        row1 = ttk.Frame(self)
        row1.pack(fill="x", padx=2, pady=(2, 0))

        self._btn(row1, "↩ Deshacer", lambda: self.text.edit_undo(),
                  "Deshacer (Ctrl+Z)")
        self._btn(row1, "↪ Rehacer", lambda: self.text.edit_redo(),
                  "Rehacer (Ctrl+Y)")
        self._sep(row1)

        self._btn(row1, "Negrita", self._make_bold,
                  "Negrita (Ctrl+B)")
        self._btn(row1, "Cursiva", self._make_italic,
                  "Cursiva (Ctrl+I)")
        self._btn(row1, "Subrayado", self._make_underline,
                  "Subrayado (Ctrl+U)")
        self._btn(row1, "Tachado", self._make_strike,
                  "Tachado")
        self._sep(row1)

        self._btn(row1, "🎨 Color", self._apply_color,
                  "Cambiar color del texto")
        self._btn(row1, "🖍 Resaltado", self._apply_bgcolor,
                  "Cambiar color de fondo")
        self._sep(row1)

        # Tipografía
        self.font_var = tk.StringVar(value="Calibri")
        fonts = sorted(set(tkfont.families()))
        font_box = ttk.Combobox(
            row1, textvariable=self.font_var, values=fonts, width=12, state="readonly"
        )
        font_box.pack(side="left", padx=2)
        font_box.bind("<<ComboboxSelected>>", lambda e: self._apply_font())
        _Tooltip(font_box, "Tipografía")

        self.size_var = tk.StringVar(value="11")
        sizes = ["8", "9", "10", "11", "12", "14", "16", "18", "20", "24"]
        size_box = ttk.Combobox(
            row1, textvariable=self.size_var, values=sizes, width=4, state="readonly"
        )
        size_box.pack(side="left", padx=2)
        size_box.bind("<<ComboboxSelected>>", lambda e: self._apply_size())
        _Tooltip(size_box, "Tamaño (pt)")

        # ── Fila 2: Párrafo, alineación, firma ──
        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=2, pady=(1, 0))

        self._btn(row2, "• Lista", self._insert_bullet,
                  "Insertar viñeta")
        self._btn(row2, "→ Sangría", self._indent_line,
                  "Aumentar sangría")
        self._btn(row2, "← Reducir", self._dedent_line,
                  "Reducir sangría")
        self._sep(row2)

        self._btn(row2, "◀ Izq", lambda: self._set_align("left"),
                  "Alinear a la izquierda")
        self._btn(row2, "≡ Centro", lambda: self._set_align("center"),
                  "Centrar texto")
        self._btn(row2, "▶ Der", lambda: self._set_align("right"),
                  "Alinear a la derecha")
        self._sep(row2)

        self._btn(row2, "🗑 Limpiar", self._clear_all,
                  "Borrar todo el contenido")
        self._sep(row2)

        # Firma integrada en la fila 2
        ttk.Label(row2, text="Firma:").pack(side="left", padx=(4, 2))
        self._sig_label = ttk.Label(
            row2, text="(ninguna)", foreground="#888888", anchor="w",
        )
        self._sig_label.pack(side="left", padx=2)
        _Tooltip(self._sig_label, "Imagen de firma que se adjuntará al correo")
        self._btn(row2, "📂 Seleccionar", self._select_signature,
                  "Elegir imagen de firma (PNG, JPG)")
        self._btn(row2, "✖ Quitar", self._remove_signature,
                  "Eliminar la firma seleccionada")

        # ── Área de texto (fondo claro para buena legibilidad) ──
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, pady=(2, 0))

        self.text = tk.Text(
            text_frame, wrap="word", undo=True, maxundo=-1,
            background="#ffffff", foreground="#000000",
            insertbackground="#000000",
            selectbackground="#3399ff", selectforeground="#ffffff",
        )
        vbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        # ── Barra de estado ──
        self._status_var = tk.StringVar(value="Listo")
        ttk.Label(
            self, textvariable=self._status_var, anchor="w", relief="sunken"
        ).pack(fill="x", padx=2, pady=(0, 2))

    def _setup_tags(self):
        self.text.tag_configure("bold")
        self.text.tag_configure("italic")
        self.text.tag_configure("underline", underline=1)
        self.text.tag_configure("strike", overstrike=1)

        self.text.tag_configure("align_left", justify="left")
        self.text.tag_configure("align_center", justify="center")
        self.text.tag_configure("align_right", justify="right")
        self.text.tag_configure("list", lmargin1=20, lmargin2=40)

    def _apply_tag_to_sel(self, tag, toggle=False, **config):
        if config:
            self.text.tag_configure(tag, **config)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return False
        if toggle:
            idx = start
            fully_tagged = True
            while self.text.compare(idx, "<", end):
                if tag not in self.text.tag_names(idx):
                    fully_tagged = False
                    break
                idx = self.text.index(f"{idx}+1c")
            if fully_tagged:
                self.text.tag_remove(tag, start, end)
            else:
                self.text.tag_add(tag, start, end)
        else:
            self.text.tag_add(tag, start, end)
        self.text.tag_add("sel", start, end)
        return True

    def _make_bold(self):
        font = tkfont.Font(
            family=self.current_font or self.default_font,
            size=int(self.current_size or self.default_size),
        )
        font.configure(weight="bold")
        self.text.tag_configure("bold", font=font)
        self.text.tag_raise("bold")
        if not self._apply_tag_to_sel("bold", toggle=True):
            if "bold" in self.active_tags:
                self.active_tags.remove("bold")
            else:
                self.active_tags.add("bold")
        self._set_status("Negrita activada" if "bold" in self.active_tags else "Negrita desactivada")

    def _make_italic(self):
        font = tkfont.Font(
            family=self.current_font or self.default_font,
            size=int(self.current_size or self.default_size),
        )
        font.configure(slant="italic")
        self.text.tag_configure("italic", font=font)
        self.text.tag_raise("italic")
        if not self._apply_tag_to_sel("italic", toggle=True):
            if "italic" in self.active_tags:
                self.active_tags.remove("italic")
            else:
                self.active_tags.add("italic")
        self._set_status("Cursiva activada" if "italic" in self.active_tags else "Cursiva desactivada")

    def _make_underline(self):
        if not self._apply_tag_to_sel("underline", toggle=True):
            if "underline" in self.active_tags:
                self.active_tags.remove("underline")
            else:
                self.active_tags.add("underline")
        self._set_status("Subrayado activado" if "underline" in self.active_tags else "Subrayado desactivado")

    def _make_strike(self):
        if not self._apply_tag_to_sel("strike", toggle=True):
            if "strike" in self.active_tags:
                self.active_tags.remove("strike")
            else:
                self.active_tags.add("strike")
        self._set_status("Tachado activado" if "strike" in self.active_tags else "Tachado desactivado")

    def _insert_bullet(self):
        line_start = self.text.index("insert linestart")
        self.text.insert(line_start, "\u2022 ")
        line_end = self.text.index(f"{line_start} lineend")
        self.text.tag_add("list", line_start, f"{line_end}+1c")
        self.text.mark_set("insert", f"{line_start}+2c")
        self._set_status("Viñeta insertada")

    def _indent_line(self):
        index = self.text.index("insert")
        line_start = self.text.index(f"{index} linestart")
        self.text.insert(line_start, "    ")
        self._set_status("Sangría aumentada")

    def _dedent_line(self):
        index = self.text.index("insert")
        line_start = self.text.index(f"{index} linestart")
        leading = self.text.get(line_start, f"{line_start}+4c")
        if leading.startswith("    "):
            self.text.delete(line_start, f"{line_start}+4c")
            self._set_status("Sangría reducida")

    def _apply_font(self):
        family = self.font_var.get()
        tag = f"font_{family.replace(' ', '_')}"
        self.text.tag_configure(tag, font=tkfont.Font(family=family))
        self.text.tag_raise(tag)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_font = family
            self._set_status(f"Tipografía activa: {family}")
            return
        self.current_font = family
        for t in self.text.tag_names():
            if t.startswith("font_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)
        self._set_status(f"Tipografía aplicada: {family}")

    def _apply_size(self):
        size = self.size_var.get()
        tag = f"size_{size}"
        self.text.tag_configure(tag, font=tkfont.Font(size=int(size)))
        self.text.tag_raise(tag)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_size = size
            self._set_status(f"Tamaño activo: {size} pt")
            return
        self.current_size = size
        for t in self.text.tag_names():
            if t.startswith("size_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)
        self._set_status(f"Tamaño aplicado: {size} pt")

    def _set_align(self, mode):
        tag = f"align_{mode}"
        try:
            start = self.text.index("sel.first linestart")
            end = self.text.index("sel.last lineend")
        except tk.TclError:
            line = self.text.index("insert")
            start = self.text.index(f"{line} linestart")
            end = self.text.index(f"{line} lineend")
        for t in ("align_left", "align_center", "align_right"):
            self.text.tag_remove(t, start, end)
        self.text.tag_add(tag, start, end)
        labels = {"left": "izquierda", "center": "centro", "right": "derecha"}
        self._set_status(f"Alineación: {labels.get(mode, mode)}")

    def _apply_color(self):
        color = colorchooser.askcolor(title="Seleccionar color del texto")[1]
        if not color:
            return
        tag = f"color_{color.lstrip('#')}"
        self.text.tag_configure(tag, foreground=color)
        self.text.tag_raise(tag)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_color = color
            self._set_status(f"Color de texto activo: {color}")
            return
        for t in self.text.tag_names():
            if t.startswith("color_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)
        self._set_status(f"Color de texto aplicado: {color}")

    def _apply_bgcolor(self):
        color = colorchooser.askcolor(title="Seleccionar color de resaltado")[1]
        if not color:
            return
        tag = f"bg_{color.lstrip('#')}"
        self.text.tag_configure(tag, background=color)
        self.text.tag_raise(tag)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_bg = color
            self._set_status(f"Color de resaltado activo: {color}")
            return
        for t in self.text.tag_names():
            if t.startswith("bg_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)
        self._set_status(f"Resaltado aplicado: {color}")

    def _on_key_release(self, event=None):
        navigation = {
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock", "Scroll_Lock",
            "Left", "Right", "Up", "Down",
            "Home", "End", "Prior", "Next", "Escape",
        }
        if event is not None:
            if event.keysym in navigation or event.char == "":
                self._update_current_styles()
                return
            if event.keysym in {"BackSpace", "Delete"}:
                self._update_current_styles()
                return
        self._apply_active_tags()
        self._update_current_styles()

    def _update_current_styles(self, event=None):
        try:
            insert_index = self.text.index("insert")
        except tk.TclError:
            return
        if self.text.compare(insert_index, ">", "1.0"):
            index = self.text.index(f"{insert_index}-1c")
        else:
            index = "1.0"
        tags = self._effective_tags(index, clean=True)
        style_tags = {t for t in tags if t in {"bold", "italic", "underline", "strike"}}
        self.active_tags = style_tags

        font_tags = [t for t in tags if t.startswith("font_")]
        if font_tags:
            font_name = font_tags[-1].split("_", 1)[1].replace("_", " ")
            self.current_font = font_name
            self.font_var.set(font_name)
        else:
            self.current_font = self.default_font
            self.font_var.set(self.default_font)

        size_tags = [t for t in tags if t.startswith("size_")]
        if size_tags:
            size_value = size_tags[-1].split("_", 1)[1]
            self.current_size = size_value
            self.size_var.set(size_value)
        else:
            self.current_size = self.default_size
            self.size_var.set(self.default_size)

        color_tags = [t for t in tags if t.startswith("color_")]
        if color_tags:
            color_value = color_tags[-1].split("_", 1)[1]
            if not color_value.startswith("#"):
                color_value = "#" + color_value
            self.current_color = color_value
        else:
            self.current_color = None

        bg_tags = [t for t in tags if t.startswith("bg_")]
        if bg_tags:
            bg_value = bg_tags[-1].split("_", 1)[1]
            if not bg_value.startswith("#"):
                bg_value = "#" + bg_value
            self.current_bg = bg_value
        else:
            self.current_bg = None

    def _effective_tags(self, index, clean=False):
        index = self.text.index(index)
        tags = [t for t in self.text.tag_names(index) if self._tag_start_html(t)]
        return self._resolve_tag_conflicts(index, tags, clean=clean)

    def _resolve_tag_conflicts(self, index, tags, clean=False):
        index = self.text.index(index)
        try:
            end = self.text.index(f"{index}+1c")
        except tk.TclError:
            end = index
        group_map: dict[str, list[str]] = {
            "font_": [], "size_": [], "color_": [], "bg_": [], "align_": []
        }
        group_order: list[str] = []
        filtered: list[str] = []
        for tag in tags:
            matched = False
            for prefix in group_map:
                if tag.startswith(prefix):
                    group_map[prefix].append(tag)
                    if prefix not in group_order:
                        group_order.append(prefix)
                    matched = True
                    break
            if not matched:
                filtered.append(tag)
        for prefix in group_order:
            candidates = group_map[prefix]
            if not candidates:
                continue
            keep = self._choose_tag_from_candidates(prefix, candidates, index)
            filtered.append(keep)
            if clean and self.text.compare(end, ">", index) and self.text.get(index, end):
                for tag in candidates:
                    if tag != keep:
                        self.text.tag_remove(tag, index, end)
        return filtered

    def _choose_tag_from_candidates(self, prefix, candidates, index):
        for delta in ("-1c", "+1c"):
            neighbor = self._neighbor_index(index, delta)
            if not neighbor:
                continue
            neighbor_tags = [t for t in self.text.tag_names(neighbor) if t.startswith(prefix)]
            if len(neighbor_tags) == 1 and neighbor_tags[0] in candidates:
                return neighbor_tags[0]
        if prefix == "size_":
            default_tag = f"{prefix}{self.default_size}"
            if default_tag in candidates:
                return default_tag
        if prefix == "font_":
            default_tag = f"{prefix}{self.default_font.replace(' ', '_')}"
            if default_tag in candidates:
                return default_tag
        return candidates[-1]

    def _neighbor_index(self, index, delta):
        try:
            neighbor = self.text.index(f"{index}{delta}")
        except tk.TclError:
            return None
        if self.text.compare(neighbor, "<", "1.0"):
            return None
        if self.text.compare(neighbor, ">=", "end"):
            return None
        if self.text.get(neighbor, f"{neighbor}+1c") == "":
            return None
        return neighbor

    def _apply_active_tags(self, event=None):
        try:
            start = self.text.index("insert-1c")
            end = self.text.index("insert")
        except tk.TclError:
            return
        if "bold" in self.active_tags:
            font = tkfont.Font(
                family=self.current_font or self.default_font,
                size=int(self.current_size or self.default_size),
                weight="bold",
            )
            self.text.tag_configure("bold", font=font)
            self.text.tag_raise("bold")
            self.text.tag_add("bold", start, end)
        if "italic" in self.active_tags:
            font = tkfont.Font(
                family=self.current_font or self.default_font,
                size=int(self.current_size or self.default_size),
                slant="italic",
            )
            self.text.tag_configure("italic", font=font)
            self.text.tag_raise("italic")
            self.text.tag_add("italic", start, end)
        for tag in self.active_tags - {"bold", "italic"}:
            self.text.tag_add(tag, start, end)
        if self.current_font:
            font_tag = f"font_{self.current_font.replace(' ', '_')}"
            self._remove_conflicting_tags("font_", font_tag, start, end)
            self.text.tag_add(font_tag, start, end)
            self.text.tag_raise(font_tag)
        if self.current_size:
            size_tag = f"size_{self.current_size}"
            self._remove_conflicting_tags("size_", size_tag, start, end)
            self.text.tag_add(size_tag, start, end)
            self.text.tag_raise(size_tag)
        if self.current_color:
            color_tag = f"color_{self.current_color.lstrip('#')}"
            self._remove_conflicting_tags("color_", color_tag, start, end)
            self.text.tag_add(color_tag, start, end)
            self.text.tag_raise(color_tag)
        if getattr(self, "current_bg", None):
            bg_tag = f"bg_{self.current_bg.lstrip('#')}"
            self._remove_conflicting_tags("bg_", bg_tag, start, end)
            self.text.tag_add(bg_tag, start, end)
            self.text.tag_raise(bg_tag)

    def _remove_conflicting_tags(self, prefix, keep_tag, start, end):
        for tag in self.text.tag_names(start):
            if tag.startswith(prefix) and tag != keep_tag:
                self.text.tag_remove(tag, start, end)

    def _handle_paste(self, event=None):
        try:
            html = self.clipboard_get(type="text/html")
        except tk.TclError:
            html = None
        if html:
            self.insert_html(html)
        else:
            try:
                text = self.clipboard_get()
            except tk.TclError:
                return "break"
            self.text.insert("insert", text)
        self._apply_active_tags()
        self._update_current_styles()
        return "break"

    def insert_html(self, html_string, index="insert"):
        try:
            from html.parser import HTMLParser
        except Exception:
            self.text.insert(index, html_string)
            return

        class Parser(HTMLParser):
            def __init__(self, widget, idx):
                super().__init__()
                self.widget = widget
                self.index = idx
                self.tag_stack = []
                self.span_stack = []

            def handle_starttag(self, tag, attrs):
                if tag in ("b", "strong"):
                    self.tag_stack.append("bold")
                elif tag in ("i", "em"):
                    self.tag_stack.append("italic")
                elif tag == "u":
                    self.tag_stack.append("underline")
                elif tag in ("s", "strike"):
                    self.tag_stack.append("strike")
                elif tag == "br":
                    self.widget.insert(self.index, "\n")
                elif tag == "li":
                    self.tag_stack.append("list")
                    self.widget.insert(self.index, "\u2022 ")
                    start = self.index
                    self.index = self.widget.index(f"{self.index}+2c")
                    self.widget.tag_add("list", start, self.index)
                elif tag in ("div", "p"):
                    style = dict(attrs).get("style", "")
                    if "text-align" in style:
                        align = style.split("text-align:")[1].split(";")[0].strip()
                        self.tag_stack.append(f"align_{align}")
                elif tag == "span":
                    style = dict(attrs).get("style", "")
                    tags = []
                    for part in style.split(";"):
                        if "font-family" in part:
                            family = part.split(":")[1].strip()
                            tag_name = f"font_{family.replace(' ', '_')}"
                            self.widget.tag_configure(tag_name, font=tkfont.Font(family=family))
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "font-size" in part:
                            size = part.split(":")[1].strip().rstrip("px").rstrip("pt")
                            tag_name = f"size_{size}"
                            self.widget.tag_configure(tag_name, font=tkfont.Font(size=int(size)))
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "color" in part:
                            color = part.split(":")[1].strip()
                            tag_name = f"color_{color.lstrip('#')}"
                            self.widget.tag_configure(tag_name, foreground=color)
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "background-color" in part:
                            color = part.split(":")[1].strip()
                            tag_name = f"bg_{color.lstrip('#')}"
                            self.widget.tag_configure(tag_name, background=color)
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                    self.span_stack.append(tags)

            def handle_endtag(self, tag):
                if tag in ("b", "strong"):
                    self._remove("bold")
                elif tag in ("i", "em"):
                    self._remove("italic")
                elif tag == "u":
                    self._remove("underline")
                elif tag in ("s", "strike"):
                    self._remove("strike")
                elif tag == "span":
                    if self.span_stack:
                        tags = self.span_stack.pop()
                        for t in tags:
                            self._remove(t)
                elif tag == "li":
                    self._remove("list")
                    self.widget.insert(self.index, "\n")
                    self.index = self.widget.index(f"{self.index}+1c")
                elif tag in ("div", "p"):
                    if self.tag_stack and self.tag_stack[-1].startswith("align_"):
                        self.tag_stack.pop()

            def _remove(self, target):
                if target in self.tag_stack:
                    self.tag_stack.reverse()
                    self.tag_stack.remove(target)
                    self.tag_stack.reverse()

            def handle_data(self, data):
                data = data.replace("\xa0", " ")
                start = self.widget.index(self.index)
                self.widget.insert(self.index, data)
                end = self.widget.index(f"{start}+{len(data)}c")
                for t in self.tag_stack:
                    self.widget.tag_add(t, start, end)
                self.index = end

        Parser(self.text, index).feed(html_string)

    # ---------- HTML Import/Export ----------
    def get_html(self):
        """Return the current text as sanitized HTML."""
        end_index = self.text.index("end-1c")
        index = "1.0"
        prev_tags = []
        html_chunks = []

        def tag_priority(tag):
            if tag == "list":
                return 0
            if tag == "bold":
                return 1
            if tag == "italic":
                return 2
            if tag == "underline":
                return 3
            if tag == "strike":
                return 4
            if tag.startswith("font_"):
                return 5
            if tag.startswith("size_"):
                return 6
            if tag.startswith("color_"):
                return 7
            if tag.startswith("bg_"):
                return 8
            if tag.startswith("align_"):
                return 9
            return 99

        while self.text.compare(index, "<=", end_index):
            char = self.text.get(index)
            raw_tags = [t for t in self.text.tag_names(index) if self._tag_start_html(t)]
            curr_tags = self._resolve_tag_conflicts(index, raw_tags, clean=False)
            for t in reversed([tg for tg in prev_tags if tg not in curr_tags]):
                html_chunks.append(self._tag_end_html(t))
            for t in sorted([tg for tg in curr_tags if tg not in prev_tags], key=tag_priority):
                html_chunks.append(self._tag_start_html(t))
            if char == " ":
                start_line = self.text.index(f"{index} linestart")
                preceding = self.text.get(start_line, index)
                if preceding == "" or preceding.isspace():
                    html_chunks.append("&nbsp;")
                else:
                    html_chunks.append(" ")
            elif char == "\n":
                if "list" not in prev_tags and "list" not in curr_tags:
                    html_chunks.append("<br>")
            else:
                html_chunks.append(escape(char))
            prev_tags = curr_tags
            index = self.text.index(f"{index}+1c")

        for t in reversed(prev_tags):
            html_chunks.append(self._tag_end_html(t))

        return "".join(html_chunks)

    def set_html(self, html_string):
        try:
            from html.parser import HTMLParser
        except Exception:
            self.text.insert("1.0", html_string)
            return

        class Parser(HTMLParser):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget
                self.tag_stack = []
                self.span_stack = []

            def handle_starttag(self, tag, attrs):
                if tag in ("b", "strong"):
                    self.tag_stack.append("bold")
                elif tag in ("i", "em"):
                    self.tag_stack.append("italic")
                elif tag == "u":
                    self.tag_stack.append("underline")
                elif tag in ("s", "strike"):
                    self.tag_stack.append("strike")
                elif tag == "br":
                    self.widget.insert("end", "\n")
                elif tag == "li":
                    self.tag_stack.append("list")
                    start = self.widget.index("end")
                    self.widget.insert("end", "\u2022 ")
                    self.widget.tag_add("list", start, "end")
                elif tag in ("div", "p"):
                    style = dict(attrs).get("style", "")
                    if "text-align" in style:
                        align = style.split("text-align:")[1].split(";")[0].strip()
                        self.tag_stack.append(f"align_{align}")
                elif tag == "span":
                    style = dict(attrs).get("style", "")
                    tags = []
                    for part in style.split(";"):
                        if "font-family" in part:
                            family = part.split(":")[1].strip()
                            tag_name = f"font_{family.replace(' ', '_')}"
                            self.widget.tag_configure(tag_name, font=tkfont.Font(family=family))
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "font-size" in part:
                            size = part.split(":")[1].strip().rstrip("px").rstrip("pt")
                            tag_name = f"size_{size}"
                            self.widget.tag_configure(tag_name, font=tkfont.Font(size=int(size)))
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "color" in part:
                            color = part.split(":")[1].strip()
                            tag_name = f"color_{color.lstrip('#')}"
                            self.widget.tag_configure(tag_name, foreground=color)
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                        elif "background-color" in part:
                            color = part.split(":")[1].strip()
                            tag_name = f"bg_{color.lstrip('#')}"
                            self.widget.tag_configure(tag_name, background=color)
                            self.tag_stack.append(tag_name)
                            tags.append(tag_name)
                    self.span_stack.append(tags)

            def handle_endtag(self, tag):
                if tag in ("b", "strong"):
                    self._remove("bold")
                elif tag in ("i", "em"):
                    self._remove("italic")
                elif tag == "u":
                    self._remove("underline")
                elif tag in ("s", "strike"):
                    self._remove("strike")
                elif tag == "span":
                    if self.span_stack:
                        tags = self.span_stack.pop()
                        for t in tags:
                            self._remove(t)
                elif tag == "li":
                    self._remove("list")
                    self.widget.insert("end", "\n")
                elif tag in ("div", "p"):
                    if self.tag_stack and self.tag_stack[-1].startswith("align_"):
                        self.tag_stack.pop()

            def _remove(self, target):
                if target in self.tag_stack:
                    self.tag_stack.reverse()
                    self.tag_stack.remove(target)
                    self.tag_stack.reverse()

            def handle_data(self, data):
                data = data.replace("\xa0", " ")
                start = self.widget.index("end-1c")
                self.widget.insert("end", data)
                end = self.widget.index("end-1c")
                for t in self.tag_stack:
                    self.widget.tag_add(t, start, end)

        self.text.delete("1.0", "end")
        Parser(self.text).feed(html_string)
        self._update_current_styles()

    @staticmethod
    def _tag_start_html(tag):
        if tag == "bold":
            return "<b>"
        if tag == "italic":
            return "<i>"
        if tag == "underline":
            return "<u>"
        if tag == "strike":
            return "<s>"
        if tag.startswith("font_"):
            family = tag.split("_", 1)[1].replace("_", " ")
            return f'<span style="font-family:{family}">'
        if tag.startswith("size_"):
            size = tag.split("_", 1)[1]
            return f'<span style="font-size:{size}px">'
        if tag.startswith("color_"):
            color = tag.split("_", 1)[1]
            if not color.startswith("#"):
                color = "#" + color
            return f'<span style="color:{color}">'
        if tag.startswith("bg_"):
            color = tag.split("_", 1)[1]
            if not color.startswith("#"):
                color = "#" + color
            return f'<span style="background-color:{color}">'
        if tag.startswith("align_"):
            mode = tag.split("_", 1)[1]
            return f'<div style="text-align:{mode}">'
        if tag == "list":
            return '<div style="margin-left:20px;text-indent:-15px">'
        return ""

    @staticmethod
    def _tag_end_html(tag):
        if tag in ("bold", "italic", "underline", "strike"):
            mapping = {"bold": "b", "italic": "i", "underline": "u", "strike": "s"}
            return f"</{mapping[tag]}>"
        if tag.startswith(("font_", "size_", "color_", "bg_")):
            return "</span>"
        if tag.startswith("align_"):
            return "</div>"
        if tag == "list":
            return "</div>"
        return ""
