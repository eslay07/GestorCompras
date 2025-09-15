from tkinter import ttk
import psutil

class ResourceStatusBar(ttk.Frame):
    """Simple status bar displaying CPU and memory usage."""
    def __init__(self, master, update_ms: int = 1000):
        super().__init__(master, style="MyFrame.TFrame")
        self.update_ms = update_ms
        self.label = ttk.Label(self, text="", style="MyLabel.TLabel")
        self.label.pack(side="right", padx=5)
        self._update_stats()

    def _update_stats(self):
        process = psutil.Process()
        mem = process.memory_info().rss / (1024 * 1024)
        cpu = psutil.cpu_percent(interval=None)
        self.label.configure(text=f"CPU: {cpu:.1f}%  MEM: {mem:.1f} MB")
        self.after(self.update_ms, self._update_stats)
