import pytest

from app.bootstrap_network import hosts_with_alias, windows_gateway


def test_gateway_comes_from_host_table_not_container_bridge():
    text = 'Iface Destination Gateway Flags RefCnt Use Metric Mask\n'
    text += 'eth0 00000000 019012AC 0003 0 0 10 00000000\n'
    text += 'docker0 000011AC 00000000 0001 0 0 0 0000FFFF\n'
    assert windows_gateway(text) == '172.18.144.1'


def test_lowest_metric_wins():
    text = 'header\na 00000000 0100000A 0003 0 0 20 00000000\n'
    text += 'b 00000000 0200000A 0003 0 0 5 00000000\n'
    assert windows_gateway(text) == '10.0.0.2'


@pytest.mark.parametrize('text', ['', 'header\ngarbage', 'header\na 00000000 00000000 0003 0 0 0 00000000'])
def test_missing_gateway_fails(text):
    with pytest.raises(ValueError):
        windows_gateway(text)


def test_alias_update_preserves_other_hosts():
    text = '127.0.0.1 localhost\n10.0.0.1 ollama.windows.host other # note\n'
    updated = hosts_with_alias(text, '10.0.0.2')
    assert '127.0.0.1 localhost' in updated
    assert '10.0.0.1 other # note' in updated
    assert updated.count('ollama.windows.host') == 1
    assert hosts_with_alias(updated, '10.0.0.3').count('ollama.windows.host') == 1


@pytest.mark.parametrize('address', ['bad', '0.0.0.0', '10.0.0.1\nevil'])
def test_invalid_override_rejected(address):
    with pytest.raises(ValueError):
        hosts_with_alias('', address)
