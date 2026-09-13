"""Local Docker fixture; never points write tests at the configured application DB."""
import asyncio
import os
import secrets
import subprocess
import time
import uuid

import pytest


def docker(*args, **kwargs):
    try:
        return subprocess.check_output(['docker', *args], text=True,
                                       stderr=subprocess.PIPE, timeout=180, **kwargs).strip()
    except (subprocess.SubprocessError, OSError):
        pytest.fail('Docker command failed; check local Docker availability.', pytrace=False)


@pytest.fixture
def isolated_neo4j(request, monkeypatch):
    if not request.config.getoption('--run-neo4j'):
        pytest.skip('Use --run-neo4j to create an isolated Docker test DB')
    import config
    from app.services.graph.store import connect

    name = 'tax-graph-test-' + uuid.uuid4().hex
    password = secrets.token_urlsafe(32)
    # Environment-only credential; never embedded in command arguments.
    env = dict(os.environ, NEO4J_AUTH='neo4j/' + password)
    try:
        docker('run', '-d', '--rm', '--name', name, '--memory', '2g',
               '-p', '127.0.0.1::7687', '-e', 'NEO4J_AUTH',
               '-e', 'NEO4J_server_memory_heap_initial__size=256m',
               '-e', 'NEO4J_server_memory_heap_max__size=512m',
               '-e', 'NEO4J_server_memory_pagecache_size=256m',
               'neo4j:5.26-community', env=env)
        port = docker('port', name, '7687/tcp').rsplit(':', 1)[1]
        monkeypatch.setattr(config, 'NEO4J_URI', 'bolt://127.0.0.1:' + port, raising=False)
        monkeypatch.setattr(config, 'NEO4J_PASSWORD', password, raising=False)
        monkeypatch.setattr(config, 'NEO4J_USER', 'neo4j', raising=False)
        monkeypatch.setattr(config, 'NEO4J_DATABASE', 'neo4j', raising=False)
        async def ready():
            async with connect() as driver:
                await driver.verify_connectivity()
        for _ in range(60):
            try:
                asyncio.run(ready())
                subprocess.run(['docker', 'exec', name, 'wget', '-q', '--spider',
                                'http://127.0.0.1:7474/'], check=True, capture_output=True, timeout=5)
                break
            except Exception:
                time.sleep(2)
        else:
            pytest.fail('Temporary Neo4j readiness timed out', pytrace=False)
        yield
    finally:
        # Exact unique test name only, including partial startup failure cleanup.
        result = subprocess.run(['docker', 'container', 'inspect', '--format', '{{.Name}}', name],
                                capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip() == '/' + name:
            docker('rm', '-f', '-v', name)
