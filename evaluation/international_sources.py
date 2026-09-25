"""Bounded KR–US/JP/CN official-source pilot. No product DB or model writes."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class Source:
    id: str
    jurisdiction: str
    topic: str
    role: str
    url: str
    format: str
    language: str
    minimum_bytes: int = 500
    edition_year: int | None = None


# Each URL is fixed and official. The pilot is intentionally not a full country's tax code.
SOURCES = (
    Source("us_code_residency", "US", "residency", "statute_edition", "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleF-chap79-sec7701.htm", "html", "en", 10000, 2024),
    Source("us_code_foreign_tax_credit", "US", "foreign_tax_credit", "statute_edition", "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapN-partIII-subpartA-sec901.htm", "html", "en", 10000, 2024),
    Source("us_irs_income_source", "US", "wages_dividends_interest", "official_guidance", "https://www.irs.gov/individuals/international-taxpayers/nonresident-aliens-sourcing-of-income", "html", "en"),
    Source("us_irs_tax_residency", "US", "residency", "official_guidance", "https://www.irs.gov/individuals/international-taxpayers/determining-an-individuals-tax-residency-status", "html", "en"),
    Source("us_irs_foreign_tax_credit", "US", "foreign_tax_credit", "official_guidance", "https://www.irs.gov/individuals/international-taxpayers/foreign-tax-credit", "html", "en"),
    Source("kr_us_treaty", "KR-US", "tax_treaty", "treaty_original", "https://www.irs.gov/pub/irs-trty/korea.pdf", "pdf", "en", 10000),
    Source("jp_income_tax_act", "JP", "residency_wages_dividends_foreign_tax_credit", "statute", "https://laws.e-gov.go.jp/api/1/lawdata/340AC0000000033", "xml", "ja", 10000),
    Source("jp_nta_income_tax_guide_2025", "JP", "individual_income_tax", "official_guidance", "https://www.nta.go.jp/english/taxes/individual/incometax_2025.htm", "html", "en", 500, 2025),
    Source("jp_nta_foreign_tax_credit", "JP", "foreign_tax_credit", "official_guidance", "https://www.nta.go.jp/english/taxes/individual/12007.htm", "html", "en"),
    Source("kr_jp_treaty", "KR-JP", "tax_treaty", "treaty_original", "https://www.mof.go.jp/tax_policy/summary/international/tax_convention/Korea1998_jp_en.pdf", "pdf", "ja+en", 10000),
    Source("kr_jp_treaty_mli_reference", "KR-JP", "tax_treaty_modification", "reference_nonbinding", "https://www.mof.go.jp/tax_policy/summary/international/tax_convention/SynthesizedTextforJapan_Korea_EN.pdf", "pdf", "en", 10000),
    Source("kr_jp_mli_application", "KR-JP", "tax_treaty_modification", "official_explanation", "https://www.mof.go.jp/english/policy/tax_policy/tax_conventions/mli_kor.htm", "html", "en"),
    Source("cn_individual_income_tax_act", "CN", "residency_wages_dividends_foreign_tax_credit", "statute", "https://www.chinatax.gov.cn/n810219/n810744/n3752930/n3752974/c3970366/content.html", "html", "zh"),
    Source("cn_individual_income_tax_act_en", "CN", "individual_income_tax", "official_translation_reference", "https://www.chinatax.gov.cn/eng/c102962/c102967/c102997/c103004/c5245849/content.html", "html", "en"),
    Source("cn_individual_income_tax_rules_en", "CN", "individual_income_tax", "official_translation_reference", "https://www.chinatax.gov.cn/eng/c102962/c102967/c102997/c103004/c5245844/content.html", "html", "en"),
    Source("kr_cn_treaty", "KR-CN", "tax_treaty", "treaty_original", "https://www.chinatax.gov.cn/n810341/n810770/c1153349/5027022/files/11533494.pdf", "pdf", "en", 10000),
    Source("kr_cn_second_protocol", "KR-CN", "tax_treaty_modification", "treaty_protocol", "https://www.chinatax.gov.cn/n810341/n810770/c1153349/5027022/files/115334910.pdf", "pdf", "en", 10000),
)

ALLOWED_HOSTS = {"www.govinfo.gov", "www.irs.gov", "laws.e-gov.go.jp", "www.nta.go.jp", "www.mof.go.jp", "www.chinatax.gov.cn"}
MAX_BYTES = 25 * 1024 * 1024


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        elif tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "br"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract_text(raw: bytes, fmt: str) -> tuple[str, int | None]:
    if fmt == "pdf":
        reader = PdfReader(BytesIO(raw))
        if not reader.pages:
            raise ValueError("PDF has no pages")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    if fmt == "xml":
        root = ET.fromstring(raw)
        return " ".join(" ".join(root.itertext()).split()), None
    parser = _VisibleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip()), None


def validate_source(source: Source, raw: bytes, content_type: str) -> tuple[str, int | None]:
    parsed = urlparse(source.url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("non-official source URL")
    if not (source.minimum_bytes <= len(raw) <= MAX_BYTES):
        raise ValueError("unexpected source size")
    if source.format == "pdf" and (not raw.startswith(b"%PDF-") or "pdf" not in content_type):
        raise ValueError("invalid PDF source")
    if source.format == "xml" and ("xml" not in content_type or b"<Law" not in raw):
        raise ValueError("invalid XML law source")
    if source.format == "html" and ("html" not in content_type or b"<html" not in raw.lower()):
        raise ValueError("invalid HTML source")
    text, pages = extract_text(raw, source.format)
    if len(text) < 200 and source.format != "pdf":
        raise ValueError("source text too short")
    return text, pages


def _write_manifest(path: Path, manifest: dict) -> None:
    draft = path.with_suffix(".tmp")
    draft.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draft.replace(path)


def audit(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    expected = {source.id: source for source in SOURCES}
    if set(manifest["records"]) != set(expected):
        raise ValueError("source inventory incomplete or contains unknown IDs")
    total_bytes = 0
    ocr_required = []
    for source_id, source in expected.items():
        record = manifest["records"][source_id]
        if record["status"] != "collected" or record["url"] != source.url:
            raise ValueError(f"source incomplete or changed: {source_id}")
        raw = output / record["raw_file"]
        txt = output / record["text_file"]
        if not raw.is_file() or not txt.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"source file integrity mismatch: {source_id}")
        if raw.stat().st_size != record["bytes"] or len(txt.read_text(encoding="utf-8")) != record["characters"]:
            raise ValueError(f"source text/size mismatch: {source_id}")
        total_bytes += record["bytes"]
        if record.get("ocr_required", source.format == "pdf" and record["characters"] < 200):
            ocr_required.append(source_id)
    return {"collected": len(expected), "countries": sorted({source.jurisdiction for source in SOURCES}), "total_bytes": total_bytes, "ocr_required": ocr_required, "reviewed": sum(item.get("review_status") == "approved" for item in manifest["records"].values())}


def write_review_index(output: Path, manifest: dict) -> None:
    rows = []
    for source in SOURCES:
        item = manifest["records"].get(source.id, {})
        if item.get("status") != "collected":
            continue
        ocr = item.get("ocr_required", source.format == "pdf" and item["characters"] < 200)
        rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><a href=\"{}\">원본</a> · <a href=\"{}\">추출 텍스트</a> · <a href=\"{}\">공식 출처</a></td><td>{}</td></tr>".format(
            escape(source.jurisdiction), escape(source.id), escape(source.topic), escape(source.role),
            escape(item["raw_file"], quote=True), escape(item["text_file"], quote=True),
            escape(source.url, quote=True), "OCR 필요" if ocr else "미검수"))
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><title>국제세무 공식자료 수집 검토</title><style>body{font:15px/1.6 sans-serif;margin:32px;max-width:1500px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;text-align:left}th{background:#eef2f7}p{color:#525c69}</style><h1>국제세무 공식자료 수집 검토</h1><p>이 파일은 원문 수집 목록입니다. 정답셋·법적 검수·서비스 검색 인덱스가 아닙니다. 시행일과 조약 적용일은 별도 검증이 필요합니다.</p><table><tr><th>관할</th><th>ID</th><th>주제</th><th>자료 성격</th><th>열기</th><th>상태</th></tr>' + "".join(rows) + "</table></html>"
    (output / "review.html").write_text(page, encoding="utf-8")


def collect(output: Path, *, resume: bool = False, pause_seconds: float = 0.5) -> dict:
    if output.exists() and not resume:
        raise FileExistsError("output exists; use --resume to retry incomplete items")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_set") != "KR-US-JP-CN-official-pilot-v1":
            raise ValueError("manifest source set mismatch")
    else:
        manifest = {"source_set": "KR-US-JP-CN-official-pilot-v1", "scope": "bounded official-source pilot; not a verified answer key or production RAG corpus", "started_at": datetime.now(timezone.utc).isoformat(), "records": {}}
    with httpx.Client(timeout=40, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (compatible; TaxAssistantResearch/1.0)"}) as client:
        for source in SOURCES:
            current = manifest["records"].get(source.id)
            if current and current.get("status") == "collected":
                if current.get("url") != source.url:
                    raise ValueError(f"source URL changed after collection: {source.id}")
                raw_path = output / current["raw_file"]
                if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != current["sha256"]:
                    raise ValueError(f"stored source integrity mismatch: {source.id}")
                continue
            base = asdict(source)
            raw_file = f"{source.id}.{source.format}"
            try:
                with client.stream("GET", source.url) as response:
                    response.raise_for_status()
                    if response.url.host != urlparse(source.url).hostname:
                        raise ValueError("source redirected to another host")
                    if int(response.headers.get("content-length", "0")) > MAX_BYTES:
                        raise ValueError("source exceeds size limit")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError("source exceeds size limit")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    text, pages = validate_source(source, raw, response.headers.get("content-type", "").lower())
                if (output / raw_file).exists():
                    raise FileExistsError(f"unindexed raw file: {raw_file}")
                with (output / raw_file).open("xb") as file:
                    file.write(raw)
                (output / f"{source.id}.txt").write_text(text, encoding="utf-8")
                manifest["records"][source.id] = {**base, "status": "collected", "raw_file": raw_file, "text_file": f"{source.id}.txt", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "characters": len(text), "pages": pages, "http_status": response.status_code, "fetched_at": datetime.now(timezone.utc).isoformat(), "effective_from": None, "effective_to": None, "review_status": "unreviewed", "text_extraction_review_required": True, "ocr_required": source.format == "pdf" and len(text) < 200}
            except (httpx.HTTPError, ValueError, FileExistsError, OSError, ET.ParseError, PdfReadError) as exc:
                manifest["records"][source.id] = {**base, "status": "failed", "error_type": type(exc).__name__}
            _write_manifest(manifest_path, manifest)
            print(json.dumps({"id": source.id, "status": manifest["records"][source.id]["status"]}, ensure_ascii=False), flush=True)
            time.sleep(pause_seconds)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)
    write_review_index(output, manifest)
    return manifest
