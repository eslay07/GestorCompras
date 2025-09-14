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
        # Track active styles to apply to newly typed text
        self.active_tags = set()
        self.current_font = self.font_var.get()
        self.current_size = self.size_var.get()
        self.current_color = None
        self.current_bg = None
        self.text.bind("<KeyRelease>", self._apply_active_tags)
        for seq in ("<<Paste>>", "<Control-v>", "<Command-v>"):
            self.text.bind(seq, self._handle_paste)

    def _create_widgets(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="B", width=2, command=self._make_bold).pack(side="left")
        ttk.Button(toolbar, text="I", width=2, command=self._make_italic).pack(side="left")
        ttk.Button(toolbar, text="U", width=2, command=self._make_underline).pack(side="left")
        ttk.Button(toolbar, text="S", width=2, command=self._make_strike).pack(side="left")
        ttk.Button(toolbar, text="\u25A3", width=2, command=self._apply_bgcolor).pack(side="left")
        ttk.Button(toolbar, text="A", width=2, command=self._apply_color).pack(side="left", padx=2)
        ttk.Button(toolbar, text="\u2022", width=2, command=self._insert_bullet).pack(side="left", padx=2)
        ttk.Button(toolbar, text="\u21E5", width=2, command=self._indent_line).pack(side="left")
        ttk.Button(toolbar, text="\u21E4", width=2, command=self._dedent_line).pack(side="left")
        ttk.Button(toolbar, text="L", width=2, command=lambda: self._set_align("left")).pack(side="left", padx=(5,0))
        ttk.Button(toolbar, text="C", width=2, command=lambda: self._set_align("center")).pack(side="left")
        ttk.Button(toolbar, text="R", width=2, command=lambda: self._set_align("right")).pack(side="left")

        self.font_var = tk.StringVar(value="Calibri")
        fonts = sorted(set(tkfont.families()))
        font_box = ttk.Combobox(
            toolbar,
            textvariable=self.font_var,
            values=fonts,
            width=10,
            state="readonly",
        )
        font_box.pack(side="left", padx=5)
        font_box.bind("<<ComboboxSelected>>", lambda e: self._apply_font())
        ttk.Button(toolbar, text="Font", command=self._apply_font).pack(side="left")

        self.size_var = tk.StringVar(value="11")
        sizes = ["8", "9", "10", "11", "12", "14", "16", "18", "20", "24"]
        size_box = ttk.Combobox(
            toolbar,
            textvariable=self.size_var,
            values=sizes,
            width=3,
            state="readonly",
        )
        size_box.pack(side="left", padx=5)
        size_box.bind("<<ComboboxSelected>>", lambda e: self._apply_size())
        ttk.Button(toolbar, text="Size", command=self._apply_size).pack(side="left")

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(text_frame, wrap="word", undo=True, maxundo=-1)
        vbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

    def _setup_tags(self):
        base = tkfont.Font(font=self.text.cget("font"))
        bold = base.copy(); bold.configure(weight="bold")
        italic = base.copy(); italic.configure(slant="italic")
        underline = base.copy(); underline.configure(underline=True)
        strike = base.copy(); strike.configure(overstrike=True)

        self.text.tag_configure("bold", font=bold)
        self.text.tag_configure("italic", font=italic)
        self.text.tag_configure("underline", font=underline)
        self.text.tag_configure("strike", font=strike)

        self.text.tag_configure("align_left", justify="left")
        self.text.tag_configure("align_center", justify="center")
        self.text.tag_configure("align_right", justify="right")

    def _apply_tag_to_sel(self, tag, toggle=False, **config):
        if config:
            self.text.tag_configure(tag, **config)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            return False
        if toggle:
            # Determine if every character in the selection already has the tag
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
        if not self._apply_tag_to_sel("bold", toggle=True):
            if "bold" in self.active_tags:
                self.active_tags.remove("bold")
            else:
                self.active_tags.add("bold")

    def _make_italic(self):
        if not self._apply_tag_to_sel("italic", toggle=True):
            if "italic" in self.active_tags:
                self.active_tags.remove("italic")
            else:
                self.active_tags.add("italic")

    def _make_underline(self):
        if not self._apply_tag_to_sel("underline", toggle=True):
            if "underline" in self.active_tags:
                self.active_tags.remove("underline")
            else:
                self.active_tags.add("underline")

    def _make_strike(self):
        if not self._apply_tag_to_sel("strike", toggle=True):
            if "strike" in self.active_tags:
                self.active_tags.remove("strike")
            else:
                self.active_tags.add("strike")

    def _insert_bullet(self):
        self.text.insert("insert", "\u2022 ")

    def _indent_line(self):
        index = self.text.index("insert")
        line_start = self.text.index(f"{index} linestart")
        self.text.insert(line_start, "    ")

    def _dedent_line(self):
        index = self.text.index("insert")
        line_start = self.text.index(f"{index} linestart")
        leading = self.text.get(line_start, f"{line_start}+4c")
        if leading.startswith("    "):
            self.text.delete(line_start, f"{line_start}+4c")

    def _apply_font(self):
        family = self.font_var.get()
        tag = f"font_{family.replace(' ', '_')}"
        self.text.tag_configure(tag, font=tkfont.Font(family=family))
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_font = family
            return
        for t in self.text.tag_names():
            if t.startswith("font_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)

    def _apply_size(self):
        size = self.size_var.get()
        tag = f"size_{size}"
        self.text.tag_configure(tag, font=tkfont.Font(size=int(size)))
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_size = size
            return
        for t in self.text.tag_names():
            if t.startswith("size_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)

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

    def _apply_color(self):
        color = colorchooser.askcolor()[1]
        if not color:
            return
        tag = f"color_{color.lstrip('#')}"
        self.text.tag_configure(tag, foreground=color)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_color = color
            return
        for t in self.text.tag_names():
            if t.startswith("color_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)

    def _apply_bgcolor(self):
        color = colorchooser.askcolor()[1]
        if not color:
            return
        tag = f"bg_{color.lstrip('#')}"
        self.text.tag_configure(tag, background=color)
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
        except tk.TclError:
            self.current_bg = color
            return
        for t in self.text.tag_names():
            if t.startswith("bg_"):
                self.text.tag_remove(t, start, end)
        self._apply_tag_to_sel(tag)

    def _apply_active_tags(self, event=None):
        try:
            start = self.text.index("insert-1c")
            end = self.text.index("insert")
        except tk.TclError:
            return
        for tag in self.active_tags:
            self.text.tag_add(tag, start, end)
        if self.current_font:
            self.text.tag_add(f"font_{self.current_font.replace(' ', '_')}", start, end)
        if self.current_size:
            self.text.tag_add(f"size_{self.current_size}", start, end)
        if self.current_color:
            self.text.tag_add(f"color_{self.current_color.lstrip('#')}", start, end)
        if getattr(self, "current_bg", None):
            self.text.tag_add(f"bg_{self.current_bg.lstrip('#')}", start, end)

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
        """Return the current text as sanitized HTML.

        The Text widget exposes formatting through tags.  To reliably
        convert the content we walk each character and compare the tags
        present at that index against the tags from the previous
        character.  Closing tags are emitted for styles that end and new
        tags are opened in a deterministic order before writing the
        actual character.  This ensures that nested styling is exported
        with valid markup and that unrecognised tags are ignored.
        """
        end_index = self.text.index("end-1c")
        index = "1.0"
        prev_tags = []
        html_chunks = []

        def tag_priority(tag):
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
            curr_tags = [t for t in self.text.tag_names(index) if self._tag_start_html(t)]
            # Close tags that no longer apply
            for t in reversed([tg for tg in prev_tags if tg not in curr_tags]):
                html_chunks.append(self._tag_end_html(t))
            # Open new tags
            for t in sorted([tg for tg in curr_tags if tg not in prev_tags], key=tag_priority):
                html_chunks.append(self._tag_start_html(t))
            if char == " ":
                start_line = self.text.index(f"{index} linestart")
                preceding = self.text.get(start_line, index)
                if preceding == "" or preceding.isspace():
                    html_chunks.append("&nbsp;")
                else:
                    html_chunks.append(" ")
            else:
                html_chunks.append(escape(char).replace("\n", "<br>"))
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
                self.span_stack = []  # Track tags introduced by <span>

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
        return ""

