import tkinter as tk
from tkinter import ttk, colorchooser
from tkinter import font as tkfont
from html import escape

class HtmlEditor(ttk.Frame):
    """Simple rich text editor that exports/imports basic HTML."""
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._create_widgets()
        self._setup_tags()

    def _create_widgets(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="B", width=2, command=self._make_bold).pack(side="left")
        ttk.Button(toolbar, text="I", width=2, command=self._make_italic).pack(side="left")
        ttk.Button(toolbar, text="U", width=2, command=self._make_underline).pack(side="left")
        ttk.Button(toolbar, text="•", width=2, command=self._insert_bullet).pack(side="left", padx=2)

        self.font_var = tk.StringVar(value="Helvetica")
        fonts = sorted(set(tkfont.families()))
        ttk.Combobox(toolbar, textvariable=self.font_var, values=fonts, width=10,
                     state="readonly").pack(side="left", padx=5)
        ttk.Button(toolbar, text="Font", command=self._apply_font).pack(side="left")

        self.size_var = tk.StringVar(value="12")
        sizes = ["10", "12", "14", "16", "18", "20", "24"]
        ttk.Combobox(toolbar, textvariable=self.size_var, values=sizes, width=3,
                     state="readonly").pack(side="left", padx=5)
        ttk.Button(toolbar, text="Size", command=self._apply_size).pack(side="left")

        ttk.Button(toolbar, text="Color", command=self._apply_color).pack(side="left", padx=5)

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(text_frame, wrap="word", undo=True, maxundo=-1)
        vbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

    def _setup_tags(self):
        self.text.tag_configure("bold", font=tkfont.Font(weight="bold"))
        self.text.tag_configure("italic", font=tkfont.Font(slant="italic"))
        self.text.tag_configure("underline", underline=True)

    def _apply_tag_to_sel(self, tag, toggle=False, **config):
        if config:
            self.text.tag_configure(tag, **config)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return
        if toggle and self.text.tag_nextrange(tag, start, end):
            self.text.tag_remove(tag, start, end)
        else:
            self.text.tag_add(tag, start, end)

    def _make_bold(self):
        self._apply_tag_to_sel("bold", toggle=True)

    def _make_italic(self):
        self._apply_tag_to_sel("italic", toggle=True)

    def _make_underline(self):
        self._apply_tag_to_sel("underline", toggle=True)

    def _insert_bullet(self):
        self.text.insert("insert", "\u2022 ")

    def _apply_font(self):
        family = self.font_var.get()
        tag = f"font_{family}"
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return
        for t in self.text.tag_names():
            if t.startswith("font_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag, font=tkfont.Font(family=family))

    def _apply_size(self):
        size = self.size_var.get()
        tag = f"size_{size}"
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return
        for t in self.text.tag_names():
            if t.startswith("size_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag, font=tkfont.Font(size=int(size)))

    def _apply_color(self):
        color = colorchooser.askcolor()[1]
        if not color:
            return
        tag = f"color_{color}"
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return
        for t in self.text.tag_names():
            if t.startswith("color_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag, foreground=color)

    # ---------- HTML Import/Export ----------
    def get_html(self):
        dump = self.text.dump("1.0", "end-1c", tag=True, text=True)
        html_chunks = []
        for index, kind, value in dump:
            if kind == "tagon":
                html_chunks.append(self._tag_start_html(value))
            elif kind == "tagoff":
                html_chunks.append(self._tag_end_html(value))
            elif kind == "text":
                html_chunks.append(escape(value).replace("\n", "<br>"))
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
            def handle_starttag(self, tag, attrs):
                if tag in ("b", "strong"):
                    self.tag_stack.append("bold")
                elif tag in ("i", "em"):
                    self.tag_stack.append("italic")
                elif tag == "u":
                    self.tag_stack.append("underline")
                elif tag == "br":
                    self.widget.insert("end", "\n")
                elif tag == "span":
                    style = dict(attrs).get("style", "")
                    for part in style.split(";"):
                        if "font-family" in part:
                            family = part.split(":")[1].strip()
                            self.tag_stack.append(f"font_{family}")
                        elif "font-size" in part:
                            size = part.split(":")[1].strip().rstrip("px").rstrip("pt")
                            self.tag_stack.append(f"size_{size}")
                        elif "color" in part:
                            color = part.split(":")[1].strip()
                            self.tag_stack.append(f"color_{color}")
            def handle_endtag(self, tag):
                if tag in ("b", "strong"):
                    self._remove("bold")
                elif tag in ("i", "em"):
                    self._remove("italic")
                elif tag == "u":
                    self._remove("underline")
                elif tag == "span":
                    if self.tag_stack:
                        self.tag_stack.pop()
            def _remove(self, target):
                if target in self.tag_stack:
                    self.tag_stack.reverse()
                    self.tag_stack.remove(target)
                    self.tag_stack.reverse()
            def handle_data(self, data):
                start = self.widget.index("end-1c")
                self.widget.insert("end", data)
                end = self.widget.index("end-1c")
                for t in self.tag_stack:
                    self.widget.tag_add(t, start, end)
        self.text.delete("1.0", "end")
        Parser(self.text).feed(html_string)

    @staticmethod
    def _tag_start_html(tag):
        if tag == "bold":
            return "<b>"
        if tag == "italic":
            return "<i>"
        if tag == "underline":
            return "<u>"
        if tag.startswith("font_"):
            family = tag.split("_", 1)[1]
            return f'<span style="font-family:{family}">'
        if tag.startswith("size_"):
            size = tag.split("_", 1)[1]
            return f'<span style="font-size:{size}px">'
        if tag.startswith("color_"):
            color = tag.split("_", 1)[1]
            return f'<span style="color:{color}">'
        return ""

    @staticmethod
    def _tag_end_html(tag):
        if tag in ("bold", "italic", "underline"):
            mapping = {"bold": "b", "italic": "i", "underline": "u"}
            return f"</{mapping[tag]}>"
        if tag.startswith(("font_", "size_", "color_")):
            return "</span>"
        return ""

