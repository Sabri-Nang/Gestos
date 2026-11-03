"""Registro de ejecuciones completas, incluida la salida de bibliotecas nativas."""

from datetime import datetime
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "log"
TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")


def run_logged(command: list[str], *, label: str, log_dir: Path = LOG_DIR) -> int:
    """Mostrar y guardar stdout/stderr combinados, conservando el código de salida."""
    log_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(TIMEZONE)
    clock = time.monotonic()
    safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=log_dir,
        prefix=f"{started:%Y-%m-%d_%H-%M-%S}_{safe_label}_", suffix=".log",
        delete=False,
    ) as log:
        print(f"Registro: {log.name}", flush=True)
        log.write(f"Inicio: {started.isoformat()}\n")
        log.write(f"Comando: {shlex.join(command)}\nDirectorio: {ROOT}\n\n")
        log.flush()
        code = 1
        try:
            with subprocess.Popen(
                command, cwd=ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1,
            ) as process:
                # El hijo comparte el grupo de la terminal y recibe Ctrl+C.
                # El padre sigue drenando la salida hasta registrar su cierre.
                previous_handler = signal.signal(signal.SIGINT, lambda *_: None)
                try:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    code = process.wait()
                    if code < 0:
                        code = 128 - code
                finally:
                    signal.signal(signal.SIGINT, previous_handler)
        except OSError as exc:
            message = f"Error al ejecutar: {exc}\n"
            log.write(message)
            print(message, file=sys.stderr, end="")
        finally:
            log.write(f"\nFin: {datetime.now(TIMEZONE).isoformat()}\n")
            log.write(f"Duración: {time.monotonic() - clock:.3f} s\nCódigo de salida: {code}\n")
        return code
