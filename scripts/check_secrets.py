"""Refuse to commit or push files that contain API keys or the local .env secrets.

Two checks, never printing a secret:
1. Known key formats (OpenRouter/OpenAI, LangSmith, Tavily, GitHub, AWS, private keys).
   Documentation placeholders such as `tvly-xxxxxxxx` are allowed.
2. When a local .env exists, the values of its secret settings (*KEY*, *SECRET*, *PASSWORD*,
   *TOKEN*) must not appear in any checked file, e.g. a real .env copied into an example.

Usage:
    python scripts/check_secrets.py            # files tracked by git (CI)
    python scripts/check_secrets.py --staged   # files staged for the next commit (pre-commit hook)
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_PATTERNS = {
    "OpenRouter/OpenAI key": re.compile(r"\bsk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{20,}"),
    "LangSmith key": re.compile(r"\blsv2_[a-z]{2}_[A-Za-z0-9_]{20,}"),
    "Tavily key": re.compile(r"\btvly-[A-Za-z0-9-]{16,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
SECRET_NAME = re.compile(r"KEY|SECRET|PASSWORD|TOKEN", re.I)
# Values that are examples, not secrets.
PLACEHOLDER = re.compile(r"(x{6,}|change-me|replace-with|your[_-]|example|test-|ci-|local-|^postgres$)", re.I)
SKIP_PARTS = ("evaluation/runs/", "node_modules/", "package-lock.json")


def placeholder(text):
    return bool(PLACEHOLDER.search(text))


def env_values(env_path):
    values = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                values[name.strip()] = value.split(" #", 1)[0].strip().strip("'\"")
    return values


def local_secrets(env_path, example_path):
    """Secret values of the real .env. Looking like an example is no exemption: a value copied from
    the README is exactly the leak to catch. Only the documented .env.example values and the local
    Docker default are skipped."""
    documented = set(env_values(example_path).values()) | {"postgres"}
    return {name: value for name, value in env_values(env_path).items()
            if SECRET_NAME.search(name) and len(value) >= 8 and value not in documented}


def problems(path, text, secrets):
    found = []
    for label, pattern in KEY_PATTERNS.items():
        if any(not placeholder(match.group(0)) for match in pattern.finditer(text)):
            found.append(label)
    found += [f"value of {name} from .env" for name, value in secrets.items() if value in text]
    return [f"{path}: {item}" for item in found]


def checked_files(staged):
    args = ["diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["ls-files"]
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [name for name in out.splitlines() if name and not any(part in name for part in SKIP_PARTS)]


def read(name, staged):
    if staged:
        # The staged content is what the commit will contain, not the working copy.
        result = subprocess.run(["git", "show", f":{name}"], cwd=ROOT, capture_output=True)
        return result.stdout.decode("utf-8", errors="ignore")
    path = ROOT / name
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def main(argv):
    staged = "--staged" in argv
    secrets = local_secrets(ROOT / ".env", ROOT / ".env.example")
    found = []
    for name in checked_files(staged):
        if name == ".env" or name.endswith("/.env"):
            found.append(f"{name}: the .env file itself must not be committed")
            continue
        found += problems(name, read(name, staged), secrets)
    if found:
        print("Secret check failed (values are not shown):")
        print("\n".join("  " + item for item in found))
        return 1
    print(f"Secret check passed ({'staged' if staged else 'tracked'} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
