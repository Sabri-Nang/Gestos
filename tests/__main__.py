"""Ejecutar pruebas guardando su salida: python -m tests [--smoke]."""

import argparse
import sys

from gesto.execution import run_logged


def main() -> int:
    parser = argparse.ArgumentParser(description="Pruebas con registro en log/.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke", action="store_true", help="Inferencia real sin cámara.")
    modes.add_argument("--preview-smoke", action="store_true", help="Vista gráfica breve y comprobación de foco.")
    args = parser.parse_args()
    if args.preview_smoke:
        command = [sys.executable, "-u", "-m", "tests.smoke_preview"]
        label = "test-preview"
    elif args.smoke:
        command = [sys.executable, "-u", "-m", "tests.smoke_vision"]
        label = "test-smoke"
    else:
        command = [sys.executable, "-u", "-m", "unittest", "discover", "-s", "tests", "-v"]
        label = "test-unit"
    return run_logged(command, label=label)


if __name__ == "__main__":
    raise SystemExit(main())
