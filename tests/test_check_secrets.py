"""The commit/CI secret check: real keys and the local .env values are refused, examples pass."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_secrets", Path(__file__).parent.parent / "scripts" / "check_secrets.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

FAKE_OPENROUTER = "sk-or-v1-" + "a1b2c3d4" * 6   # built at runtime so this file holds no key-shaped literal


def test_key_formats_are_refused_but_documentation_placeholders_pass():
    assert check.problems("a.py", f"key = '{FAKE_OPENROUTER}'", {}) == ["a.py: OpenRouter/OpenAI key"]
    assert check.problems("b.md", "TAVILY_API_KEY=" + "tvly-" + "Q7rT9wX2" * 3, {}) == ["b.md: Tavily key"]
    assert check.problems("c.md", "TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx", {}) == []
    assert check.problems("d.md", "-----BEGIN " + "RSA PRIVATE KEY-----", {}) == ["d.md: private key"]


def test_a_value_from_the_real_env_is_refused_even_if_it_reads_like_an_example(tmp_path):
    env, example = tmp_path / ".env", tmp_path / ".env.example"
    example.write_text("JWT_SECRET=replace-with-a-long-random-secret\nPOSTGRES_PASSWORD=change-me\n", encoding="utf-8")
    env.write_text("JWT_SECRET=your-example-secret-for-dev\nPOSTGRES_PASSWORD=postgres\n"
                   "OPENROUTER_API_KEY=\nLLM_PROVIDER=openrouter\n", encoding="utf-8")
    secrets = check.local_secrets(env, example)
    assert secrets == {"JWT_SECRET": "your-example-secret-for-dev"}   # empty, short and documented values skipped
    assert check.problems("README.md", "JWT_SECRET=your-example-secret-for-dev", secrets) == [
        "README.md: value of JWT_SECRET from .env"]
    env.write_text("JWT_SECRET=replace-with-a-long-random-secret\n", encoding="utf-8")
    assert check.local_secrets(env, example) == {}   # the documented example itself is not a secret


def test_the_repository_holds_no_secret_now():
    import shutil
    import pytest
    if not shutil.which("git") or not (Path(__file__).parent.parent / ".git").exists():
        pytest.skip("needs a git checkout (CI and development clones have one)")
    assert check.main([]) == 0
