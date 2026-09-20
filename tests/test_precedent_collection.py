import pytest
from evaluation.precedents import redact, write


def test_credential_urls_redacted():
    assert redact('https://x.test/?OC=secret&target=prec') == 'https://x.test/?OC=REDACTED&target=prec'
    assert 'secret' not in redact('OC%3Dsecret&x=1')


def test_existing_artifacts_not_overwritten(tmp_path):
    path=tmp_path/'record.json'
    write(path,{'original':True})
    with pytest.raises(FileExistsError):
        write(path,{'original':False})
