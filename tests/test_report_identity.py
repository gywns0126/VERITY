"""Offline PDF identity regression: embedded PNG, vector flag and safe failures."""
import copy
import io
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
import report_identity


def png():
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0\0\xff\0' * 2))
            + chunk(b'IEND', b''))


@pytest.fixture(autouse=True)
def clear_logo_cache():
    report_identity._CACHE.clear()
    yield
    report_identity._CACHE.clear()


def mock_cdn(monkeypatch, payload):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout))
            if isinstance(payload, Exception):
                raise payload
            return io.BytesIO(payload)
    monkeypatch.setattr(report_identity.urllib.request, 'build_opener', lambda *args: Opener())
    return calls


def test_png_is_bounded_cached_and_ticker_path_is_normalized(monkeypatch):
    raw = png()
    calls = mock_cdn(monkeypatch, raw)
    assert report_identity.logo_png('BRK-B') == raw
    assert report_identity.logo_png('BRK.B') == raw
    assert calls == [('https://static.toss.im/png-icons/securities/icn-sec-fill-BRK.B.png', 1)]


@pytest.mark.parametrize('ticker', ['https://evil.example/a', '../foo', 'CAT?x=y', 'A/B', '', 'A' * 11])
def test_untrusted_input_cannot_become_a_fetch_url(monkeypatch, ticker):
    calls = mock_cdn(monkeypatch, png())
    assert report_identity.logo_png(ticker) == b''
    assert not calls


@pytest.mark.parametrize('payload', [b'<html>not a logo</html>', b'\x89PNG\r\n\x1a\n',
                                    b'x' * (report_identity._MAX_BYTES + 1), TimeoutError()])
def test_invalid_missing_and_timeout_logos_fail_closed(monkeypatch, payload):
    calls = mock_cdn(monkeypatch, payload)
    assert report_identity.logo_png('005930') == b''
    assert report_identity.logo_png('005930') == b''
    assert len(calls) == 1


def test_negative_cache_expires_and_cache_size_is_bounded(monkeypatch):
    calls = mock_cdn(monkeypatch, b'bad')
    clock = [0]
    monkeypatch.setattr(report_identity.time, 'monotonic', lambda: clock[0])
    report_identity.logo_png('CAT')
    clock[0] = 61
    report_identity.logo_png('CAT')
    assert len(calls) == 2
    for index in range(130):
        report_identity.logo_png(f'{index:06}')
    assert len(report_identity._CACHE) == 128


def test_redirects_to_other_hosts_are_never_followed():
    assert report_identity._NoRedirect().redirect_request(
        None, None, 302, '', {}, 'http://127.0.0.1/private') is None


def test_dripping_body_is_stopped_by_elapsed_budget(monkeypatch):
    clock = [0]
    class Drip(io.BytesIO):
        def read1(self, size):
            clock[0] += 0.6
            return b'x'
    class Opener:
        def open(self, *args, **kwargs):
            return Drip()
    monkeypatch.setattr(report_identity.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(report_identity.urllib.request, 'build_opener', lambda *args: Opener())
    assert report_identity.logo_png('CAT') == b''
    assert clock[0] < 3


def test_missing_or_malformed_local_flag_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(report_identity, '_FLAG_DIR', tmp_path)
    assert report_identity.flag_svg('KR') == ''
    (tmp_path / 'us.svg').write_text('<svg broken')
    assert report_identity.flag_svg('US') == ''


def dossier(ticker):
    from report_evidence import build_report
    filename = 'stock_report_public.json' if ticker.isdigit() else 'us_stock_report_public.json'
    return build_report(ticker, lambda name: {'stocks': {ticker: {'ticker': ticker, 'name': '검증 기업'}}}
                        if name == filename else {})


@pytest.mark.parametrize('ticker,market', [('005930', 'KR'), ('CAT', 'US')])
def test_real_pdf_embeds_logo_and_local_flag_without_polluting_evidence(monkeypatch, ticker, market):
    pytest.importorskip('typst')
    from pypdf import PdfReader
    from fact_report import _render
    from report_evidence import analysis_prompt
    monkeypatch.setattr(report_identity, 'logo_png', lambda ticker: png())
    data = dossier(ticker)
    assert data and data['market'] == market
    original = copy.deepcopy(data)
    pdf = PdfReader(io.BytesIO(_render(data)))
    first = pdf.pages[0]
    assert any(image.image.size == (2, 2) for image in first.images)
    assert market in first.extract_text() and ticker in first.extract_text()
    # Circle-flags remain local vector assets, not fragile network image URLs.
    flags = Path(__file__).resolve().parents[1] / 'vercel-api/api/_templates/flags'
    assert (flags / (market.lower() + '.svg')).is_file()
    assert data == original
    assert 'logo_png' not in analysis_prompt(data)


def test_corrupt_png_does_not_block_pdf_text_or_country(monkeypatch):
    pytest.importorskip('typst')
    from pypdf import PdfReader
    from fact_report import _render
    corrupt = png()[:24]  # Has a valid PNG header, but cannot be decoded.
    calls = mock_cdn(monkeypatch, corrupt)
    assert report_identity.logo_png('CAT') == corrupt
    text = PdfReader(io.BytesIO(_render(dossier('CAT')))).pages[0].extract_text()
    assert '검증 기업' in text and 'CAT · US' in text
    assert report_identity.logo_png('CAT') == b''
    assert len(calls) == 1


def test_missing_flag_still_renders_report_with_embedded_logo(monkeypatch, tmp_path):
    pytest.importorskip('typst')
    from pypdf import PdfReader
    from fact_report import _render
    monkeypatch.setattr(report_identity, '_FLAG_DIR', tmp_path)
    monkeypatch.setattr(report_identity, 'logo_png', lambda ticker: png())
    first = PdfReader(io.BytesIO(_render(dossier('CAT')))).pages[0]
    assert 'CAT · US' in first.extract_text() and len(list(first.images)) == 1
