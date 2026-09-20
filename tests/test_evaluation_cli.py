"""The evaluation launcher and its safe exit-code contract."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from evaluation import cli
from evaluation.runner import NoEligibleCases


def test_launcher_help():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / 'scripts/evaluate.py'), '--help'],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert 'validate,run,suite,score,compare,langsmith' in result.stdout


def test_validate(capsys):
    assert cli.entrypoint(['validate', '--dataset', 'evaluation/datasets/contracts.json']) == 0
    assert json.loads(capsys.readouterr().out)['cases'] == 22


@pytest.mark.parametrize('error,code', [(NoEligibleCases('private detail'), 2), (ValueError('private detail'), 3)])
def test_safe_error_exit(monkeypatch, capsys, error, code):
    def fail(argv):
        raise error
    monkeypatch.setattr(cli, 'main', fail)
    assert cli.entrypoint([]) == code
    assert 'private detail' not in capsys.readouterr().err


@pytest.mark.parametrize('code', [0, 1, 2])
def test_gate_exit_passthrough(monkeypatch, code):
    monkeypatch.setattr(cli, 'main', lambda argv: code)
    assert cli.entrypoint([]) == code
