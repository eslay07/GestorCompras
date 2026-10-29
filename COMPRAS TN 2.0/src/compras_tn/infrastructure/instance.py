"""Shared installation/application lease, held until the owning process exits."""
from pathlib import Path


class DataLease:
    def __init__(self, root: Path):
        import msvcrt
        root.mkdir(parents=True, exist_ok=True)
        self.stream = (root / "application.lock").open("a+b")
        self.stream.seek(0, 2)
        if not self.stream.tell():
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.stream.close()
            raise RuntimeError("COMPRAS TN está abierto o hay otra instalación en curso. Cierre la aplicación y vuelva a intentar.") from exc

    def close(self):
        import msvcrt
        if not self.stream.closed:
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
