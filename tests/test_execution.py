import contextlib
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

from gesto.execution import run_logged


class ExecutionLogTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Requiere señales de un grupo de procesos POSIX.")
    def test_ctrl_c_preserves_cleanup_output_and_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            child = 'import time\ntry:\n print("ready", flush=True)\n time.sleep(20)\nfinally:\n print("cleanup", flush=True)'
            script = (
                "from pathlib import Path; import sys; "
                "from gesto.execution import run_logged; "
                f"sys.exit(run_logged([sys.executable, '-u', '-c', {child!r}], "
                f"label='interrupt', log_dir=Path({directory!r})))"
            )
            with subprocess.Popen(
                [sys.executable, "-u", "-c", script], start_new_session=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            ) as process:
                try:
                    self.assertIn("Registro:", process.stdout.readline())
                    self.assertEqual(process.stdout.readline().strip(), "ready")
                    os.killpg(process.pid, signal.SIGINT)
                    output, _ = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 130)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            content = next(Path(directory).glob("*.log")).read_text()
        self.assertIn("cleanup", output)
        self.assertIn("cleanup", content)
        self.assertIn("Código de salida: 130", content)

    def test_records_stdout_native_stderr_and_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(io.StringIO()) as console:
                code = run_logged(
                    [sys.executable, "-u", "-c",
                     'import os; print("salida normal"); os.write(2, b"error nativo\\n"); raise SystemExit(3)'],
                    label="failure", log_dir=Path(directory),
                )
            logs = list(Path(directory).glob("*.log"))
            self.assertEqual(len(logs), 1)
            content = logs[0].read_text()
        self.assertEqual(code, 3)
        for text in ("salida normal", "error nativo"):
            self.assertIn(text, console.getvalue())
            self.assertIn(text, content)
        for text in ("Inicio:", "Comando:", "Directorio:", "Fin:", "Duración:", "Código de salida: 3"):
            self.assertIn(text, content)

    def test_successful_runs_have_distinct_files(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = run_logged(
                        [sys.executable, "-c", 'print("ok")'],
                        label="success", log_dir=Path(directory),
                    )
                self.assertEqual(code, 0)
            self.assertEqual(len(list(Path(directory).glob("*.log"))), 2)


if __name__ == "__main__":
    unittest.main()
