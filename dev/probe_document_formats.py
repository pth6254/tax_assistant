"""Live upload-to-vector smoke test for all supported formats and scanned PDF OCR."""
from io import BytesIO
import json
import subprocess
import uuid
import zipfile

import httpx
from PIL import Image, ImageDraw, ImageFont
import psycopg
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.security import create_access_token
from config import DATABASE_URL


def zipped(parts):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return output.getvalue()


def scanned_pdf():
    image = Image.new('RGB', (1400, 400), 'white')
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 72)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((50, 125), 'TAX INVOICE 2024', fill='black', font=font)
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawImage(ImageReader(image), 35, 430, width=520, height=150)
    pdf.save()
    return output.getvalue()


def fixtures():
    return {
        'docx': zipped({'word/document.xml': '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>DOCX tax evidence 2024</w:t></w:r></w:p></w:body></w:document>'}),
        'hwpx': zipped({'Contents/section0.xml': '<hp:sec xmlns:hp="urn:hp"><hp:p><hp:run><hp:t>HWPX tax evidence 2024</hp:t></hp:run></hp:p></hp:sec>'}),
        'pptx': zipped({'ppt/presentation.xml': '<presentation/>',
                        'ppt/slides/slide1.xml': '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:t>PPTX tax evidence 2024</a:t></a:p></p:sld>'}),
        'html': b'<html><body><h1>HTML tax evidence 2024</h1><script>hidden_code</script></body></html>',
        'pdf': scanned_pdf(),
    }


def main():
    email = f'format-probe-{uuid.uuid4().hex}@example.invalid'
    uid = None
    with psycopg.connect(DATABASE_URL) as database:
        try:
            with database.cursor() as cursor:
                cursor.execute('INSERT INTO users(email,password) VALUES(%s,%s) RETURNING id',
                               (email, 'probe-account-no-login'))
                uid = cursor.fetchone()[0]
            database.commit()
            token = create_access_token(str(uid), email)
            with httpx.Client(base_url='http://localhost:3002',
                              cookies={'access_token': token}, timeout=180, trust_env=False) as api:
                originals = fixtures()
                names = {}
                for suffix, content in originals.items():
                    name = f'소득세법(법률)_format_probe_{uuid.uuid4().hex}.{suffix}'
                    names[suffix] = name
                    response = api.post('/api/upload', files={'file': (name, content, 'application/octet-stream')})
                    assert response.status_code == 200, (suffix, response.status_code, response.text[:500])
                    result = response.json()
                    assert result['chunks_stored'] > 0 and result['format'] == suffix
                    assert (result['ocr_pages'] == 1) == (suffix == 'pdf')
                    original = api.get('/api/documents/' + name + '/file')
                    assert original.status_code == 200 and original.content == content
                    if suffix == 'html':
                        assert original.headers['content-disposition'].startswith('attachment;')
                listing = api.get('/api/documents')
                assert listing.status_code == 200
                listed = {row['filename']: row for row in listing.json()}
                if not all(name in listed for name in names.values()):
                    with database.cursor() as cursor:
                        cursor.execute("SELECT metadata::text FROM documents WHERE user_id=%s LIMIT 8", (uid,))
                        print('upload metadata diagnosis:', [row[0] for row in cursor.fetchall()])
                    print('listed names:', list(listed))
                for suffix, name in names.items():
                    assert listed[name]['search_ready'] and listed[name]['original_available']
                    assert listed[name]['format'] == suffix
                    assert listed[name]['chunking_version'] == 2
                with database.cursor() as cursor:
                    cursor.execute('''SELECT metadata->>'source',string_agg(content,'\n'),count(embedding),
                        jsonb_agg(metadata)
                        FROM documents WHERE user_id=%s GROUP BY metadata->>'source' ''', (uid,))
                    rows = {name: (text, count, metadata) for name, text, count, metadata in cursor.fetchall()}
                for suffix, name in names.items():
                    body, vectors, metadata = rows[name]
                    expected = 'TAX INVOICE' if suffix == 'pdf' else suffix.upper()
                    assert vectors > 0 and expected in body, (suffix, body[:200])
                    location_key = {'pdf': 'page', 'pptx': 'slide', 'hwpx': 'section'}.get(suffix)
                    if location_key:
                        assert any(item.get(location_key) == 1 for item in metadata), (suffix, metadata)
                    if suffix == 'pdf':
                        assert any(item.get('ocr') is True for item in metadata), metadata
                    if suffix == 'html':
                        assert 'hidden_code' not in body
                search_code = (
                    'import asyncio,json,os;'
                    'from app.services.search.hybrid_search_service import search_user_documents;'
                    'hits=asyncio.run(search_user_documents("DOCX tax evidence 2024",os.environ["PROBE_UID"],5));'
                    'print(json.dumps([hit.source for hit in hits],ensure_ascii=False))'
                )
                search = subprocess.run(['docker', 'exec', '-e', f'PROBE_UID={uid}',
                                         'tax_backend', 'python', '-c', search_code],
                                        capture_output=True, text=True, timeout=60, check=True)
                hits = json.loads(search.stdout.strip().splitlines()[-1])
                assert names['docx'] in hits, hits
                print('live upload/RAG vectors: PDF OCR, DOCX, HWPX, PPTX, HTML passed')
        finally:
            if uid:
                with database.cursor() as cursor:
                    cursor.execute('DELETE FROM documents WHERE user_id=%s', (uid,))
                    cursor.execute('DELETE FROM user_document_files WHERE user_id=%s', (uid,))
                    cursor.execute('DELETE FROM users WHERE id=%s', (uid,))
                database.commit()


if __name__ == '__main__':
    main()
