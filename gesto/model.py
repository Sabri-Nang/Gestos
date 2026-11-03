"""Modelo oficial versionado y verificado antes de usarlo."""

import hashlib
from pathlib import Path
import tempfile
import urllib.request

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
# SHA-256 del artefacto descargado del origen oficial (versión 1).
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def verify_model(path: Path = MODEL_PATH) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Falta el modelo en {path}. Ejecutá: python -m gesto download-model"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError(f"Checksum incorrecto en {path}. Volvé a descargar el modelo.")


def download_model() -> None:
    if MODEL_PATH.exists():
        verify_model()
        print(f"Modelo ya disponible y verificado: {MODEL_PATH}")
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=MODEL_PATH.parent, suffix=".part", delete=False
        ) as destination:
            temporary = Path(destination.name)
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
                while chunk := response.read(64 * 1024):
                    destination.write(chunk)
        verify_model(temporary)
        temporary.replace(MODEL_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Modelo descargado y verificado: {MODEL_PATH}")
