"""Framework reutilizable de wizard paso a paso."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras import theme
from gestorcompras.ui.common import add_hover_effect


class WizardStep:
    """Descriptor de un paso del wizard."""

    def __init__(self, title: str, build_fn, *, validate_fn=None):
        self.title = title
        self.build_fn = build_fn
        self.validate_fn = validate_fn


class WizardFrame(ttk.Frame):
    """Contenedor que muestra pasos secuenciales con indicador de progreso."""

    def __init__(
        self,
        master: tk.Misc,
        steps: list[WizardStep],
        *,
        on_finish=None,
        finish_label: str = "Ejecutar",
    ):
        super().__init__(master, style="MyFrame.TFrame")
        self._steps = steps
        self._on_finish = on_finish
        self._finish_label = finish_label
        self._current = 0
        self._step_frames: list[ttk.Frame] = []
        self._indicators: list[tuple[tk.Canvas, tk.Label]] = []

        self._build()
        self._show_step(0)

    def _build(self) -> None:
        self._header = ttk.Frame(self, style="MyFrame.TFrame")
        self._header.pack(fill="x", padx=24, pady=(18, 6))
        self._build_indicators()

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=16)

        self._body = ttk.Frame(self, style="MyFrame.TFrame")
        self._body.pack(fill="both", expand=True, padx=24, pady=(12, 6))

        for step in self._steps:
            frame = ttk.Frame(self._body, style="MyFrame.TFrame")
            step.build_fn(frame)
            self._step_frames.append(frame)

        nav_sep = ttk.Separator(self, orient="horizontal")
        nav_sep.pack(fill="x", padx=16)

        self._nav = ttk.Frame(self, style="MyFrame.TFrame")
        self._nav.pack(fill="x", padx=24, pady=12)

        self._btn_prev = ttk.Button(
            self._nav, text="Anterior", style="MyButton.TButton",
            command=self._go_prev,
        )
        self._btn_prev.pack(side="left")
        add_hover_effect(self._btn_prev)

        self._btn_next = ttk.Button(
            self._nav, text="Siguiente", style="MyButton.TButton",
            command=self._go_next,
        )
        self._btn_next.pack(side="right")
        add_hover_effect(self._btn_next)

    def _build_indicators(self) -> None:
        for widget in self._header.winfo_children():
            widget.destroy()
        self._indicators.clear()

        center = ttk.Frame(self._header, style="MyFrame.TFrame")
        center.pack(anchor="center")

        for i, step in enumerate(self._steps):
            if i > 0:
                line = tk.Frame(center, bg=theme.color_borde, height=2, width=40)
                line.pack(side="left", padx=2, pady=0)

            item = ttk.Frame(center, style="MyFrame.TFrame")
            item.pack(side="left", padx=4)

            circle = tk.Canvas(item, width=28, height=28,
                               bg=theme.bg_frame, highlightthickness=0)
            circle.pack(side="left")
            circle.create_oval(2, 2, 26, 26, fill=theme.color_borde, outline="", tags="bg")
            circle.create_text(14, 14, text=str(i + 1), fill="#FFFFFF",
                               font=("Segoe UI", 10, "bold"), tags="num")

            lbl = tk.Label(item, text=step.title, font=("Segoe UI", 10),
                           bg=theme.bg_frame, fg=theme.color_texto)
            lbl.pack(side="left", padx=(4, 0))

            self._indicators.append((circle, lbl))

    def _update_indicators(self) -> None:
        for i, (circle, lbl) in enumerate(self._indicators):
            if i < self._current:
                color = theme.color_success
                fg = theme.color_success
            elif i == self._current:
                color = theme.color_primario
                fg = theme.color_primario
            else:
                color = theme.color_borde
                fg = theme.color_texto
            circle.itemconfigure("bg", fill=color)
            lbl.configure(fg=fg)

    def _show_step(self, index: int) -> None:
        for f in self._step_frames:
            f.pack_forget()
        self._step_frames[index].pack(fill="both", expand=True)
        self._current = index
        self._update_indicators()
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        is_first = self._current == 0
        is_last = self._current == len(self._steps) - 1

        self._btn_prev.configure(state="disabled" if is_first else "normal")

        if is_last:
            self._btn_next.configure(text=self._finish_label)
        else:
            self._btn_next.configure(text="Siguiente")

    def _go_prev(self) -> None:
        if self._current > 0:
            self._show_step(self._current - 1)

    def _go_next(self) -> None:
        step = self._steps[self._current]
        if step.validate_fn and not step.validate_fn():
            return

        if self._current < len(self._steps) - 1:
            self._show_step(self._current + 1)
        elif self._on_finish:
            self._on_finish()

    @property
    def current_step(self) -> int:
        return self._current

    def go_to_step(self, index: int) -> None:
        if 0 <= index < len(self._steps):
            self._show_step(index)

    def set_nav_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._btn_prev.configure(state=state)
        self._btn_next.configure(state=state)
