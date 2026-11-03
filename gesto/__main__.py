"""Comandos de desarrollo: python -m gesto --help."""

import argparse
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
import os
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, load_settings


def nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Debe ser un entero mayor o igual a cero.")
    return number


def confidence(value: str) -> float:
    number = float(value)
    if not 0 < number <= 1:
        raise argparse.ArgumentTypeError("La confianza debe estar entre 0 (exclusivo) y 1.")
    return number


def doctor(*, check_keyboard=False) -> None:
    from .model import MODEL_PATH, verify_model

    print(f"Python: {sys.version.split()[0]} | {sys.executable}")
    for package in ("mediapipe", "opencv-contrib-python", "numpy", "PyAutoGUI"):
        try:
            print(f"{package}: {version(package)}")
        except PackageNotFoundError:
            print(f"{package}: NO INSTALADO")
    print(f"Sesión: {os.environ.get('XDG_SESSION_TYPE', 'desconocida')}")
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("Pendiente validar envío de teclas mediante X11/XWayland.")
    try:
        verify_model()
        print(f"Modelo: checksum correcto ({MODEL_PATH})")
    except (OSError, ValueError) as exc:
        print(f"Modelo: {exc}")
    if check_keyboard:
        from .keyboard import KeyboardSender
        KeyboardSender()
        print("Teclado: PyAutoGUI inicializado. No se enviaron teclas ni se movió el mouse.")
    else:
        print("Este informe no abre la cámara ni prueba el escritorio.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gesto: primeras herramientas del MVP para Canva.")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor", help="Informar versiones, sesión gráfica y modelo.")
    doctor_parser.add_argument("--keyboard", action="store_true",
                               help="Comprobar conexión de PyAutoGUI sin enviar teclas.")
    commands.add_parser("download-model", help="Descargar y verificar el modelo oficial.")
    for name, help_text in (("camera", "Mostrar landmarks y FPS; no envía teclas."),
                            ("simulate", "Reconocer barridos sin enviar teclas a Canva."),
                            ("present", "Controlar Canva con barridos y pausa por puño.")):
        camera = commands.add_parser(name, help=help_text)
        camera.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        camera.add_argument("--camera", type=nonnegative, help="Índice de cámara.")
        camera.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=None)
        camera.add_argument("--confidence", type=confidence)
        if name != "camera":
            camera.add_argument("--distance", type=confidence,
                                help="Desplazamiento mínimo como fracción del ancho.")
            camera.add_argument("--cooldown-ms", type=nonnegative)
            camera.add_argument("--stable-ms", type=nonnegative)
            camera.add_argument("--min-duration-ms", type=nonnegative)
            camera.add_argument("--max-duration-ms", type=nonnegative)
        if name == "present":
            camera.add_argument("--preview", action=argparse.BooleanOptionalAction, default=False,
                                help="Mostrar diagnóstico (por defecto no abre ventana).")
            camera.add_argument("--no-fist-control", action="store_true",
                                help="Iniciar tras la cuenta regresiva y desactivar el control por puño.")
    keyboard = commands.add_parser("keyboard-test", help="Simular o enviar una única pulsación.")
    keyboard.add_argument("--action", choices=("next", "previous"), default="next")
    keyboard_mode = keyboard.add_mutually_exclusive_group()
    keyboard_mode.add_argument("--send", action="store_true", help="Enviar realmente la tecla.")
    keyboard_mode.add_argument("--focus-only", action="store_true",
                               help="Informar la ventana X11 enfocada sin enviar teclas.")
    keyboard.add_argument("--countdown", type=nonnegative, default=5)
    keyboard.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 12):
        print("Error: este MVP requiere Python 3.12. Activá .venv.", file=sys.stderr)
        return 1
    try:
        if args.command == "doctor":
            doctor(check_keyboard=args.keyboard)
        elif args.command == "download-model":
            from .model import download_model
            download_model()
        elif args.command in ("camera", "simulate", "present"):
            from .vision import run_camera
            from .gestures import GestureDetector
            settings = load_settings(args.config)
            camera_options = {name: value for name, value in (
                ("index", args.camera), ("mirror", args.mirror), ("confidence", args.confidence)
            ) if value is not None}
            camera_settings = replace(settings.camera, **camera_options)
            detector = None
            controller = None
            if args.command != "camera":
                overrides = {name: getattr(args, name) for name in (
                    "distance", "cooldown_ms", "stable_ms", "min_duration_ms", "max_duration_ms"
                ) if getattr(args, name) is not None}
                detector = GestureDetector(replace(settings.gestures, **overrides))
            if args.command == "present":
                from .keyboard import KeyboardSender
                from .presentation import PresentationController
                sender = KeyboardSender({"next": settings.keys.next, "previous": settings.keys.previous})
                controller = PresentationController(detector, sender, settings.presentation,
                                                    fist_control=not args.no_fist_control)
            print(f"Configuración: {args.config.resolve()} | {camera_settings}", flush=True)
            run_camera(camera_settings.index, mirror=camera_settings.mirror,
                       confidence=camera_settings.confidence, detector=detector,
                       controller=controller, preview=args.preview if controller else True)
        elif args.command == "keyboard-test":
            from .keyboard import probe_keyboard
            settings = load_settings(args.config)
            probe_keyboard(args.action, send=args.send, countdown=args.countdown,
                           keys={"next": settings.keys.next, "previous": settings.keys.previous},
                           focus_only=args.focus_only)
    except KeyboardInterrupt:
        print("\nOperación cancelada.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    from .execution import run_logged

    raise SystemExit(run_logged(
        [sys.executable, "-u", "-m", "gesto._entry", *sys.argv[1:]],
        label=sys.argv[1] if len(sys.argv) > 1 else "help",
    ))
