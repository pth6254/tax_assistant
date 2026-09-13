"""Non-destructive shell regression tests; run with unittest in WSL."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dev/docker-down-wsl.sh"


@unittest.skipUnless(os.name == "posix", "Requires WSL/Linux bash")
class DockerDownScriptTests(unittest.TestCase):
    def run_script(self, *args, docker_exit="0"):
        with tempfile.TemporaryDirectory(prefix="tax-down-test-") as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text(
                '#!/bin/bash\nprintf "%s\\n" "$PWD" "$OLLAMA_WINDOWS_IP" "$@" > "$TEST_LOG"\n'
                'exit "$TEST_DOCKER_EXIT"\n', encoding="utf-8"
            )
            docker.chmod(0o700)
            log = root / "calls"
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       TEST_LOG=str(log), TEST_DOCKER_EXIT=docker_exit)
            env.pop("OLLAMA_WINDOWS_IP", None)
            result = subprocess.run(["bash", str(SCRIPT), *args], cwd=root,
                                    env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_down_from_other_directory_without_ollama_ip(self):
        result, call = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(call, [str(SCRIPT.parents[1]), "127.0.0.1", "compose",
                               "-f", "docker-compose.yml", "-f",
                               "docker-compose.llamacpp.yml",
                               "down", "--timeout", "30"])

    def test_dry_run_only_validates_config(self):
        result, call = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(call[-2:], ["config", "--quiet"])
        self.assertNotIn("down", call)

    def test_rejects_destructive_or_unknown_arguments(self):
        for argument in ("-v", "--volumes", "--rmi", "--remove-orphans", "backend"):
            with self.subTest(argument=argument):
                result, call = self.run_script(argument)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(call, [])

    def test_help_does_not_call_docker(self):
        result, call = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(call, [])

    def test_docker_failure_is_propagated(self):
        for args in ((), ("--dry-run",)):
            result, _ = self.run_script(*args, docker_exit="17")
            self.assertEqual(result.returncode, 17)
            self.assertNotIn("[OK]", result.stdout)


if __name__ == "__main__":
    unittest.main()
