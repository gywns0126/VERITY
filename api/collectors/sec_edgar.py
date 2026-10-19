"""
SEC EDGAR 미국 공시 데이터 수집기 (DART 대체)
- 최근 공시 목록 (10-K, 10-Q, 8-K)
- 내부자 거래 (Form 4)
- XBRL 핵심 재무 추출 (FCF, 순이익, 부채비율 → Brain용)
- 8-K 리스크 키워드 전문 탐지 (EFTS full-text search)

Rate limit: 10 req/sec, User-Agent 필수
"""
import logging
import math
import re
import time
from datetime import date

import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE = "https://efts.sec.gov/LATEST"
_DATA_BASE = "https://data.sec.gov"  # submissions/CIK + /api/xbrl/companyfacts/CIK
# 2026-05-18 fix — /files/company_tickers.json 만 www.sec.gov 로 이전됨 (data.sec.gov = 404).
# workflow log trace: SEC CIK resolve failed for CRM/BAC/...: 404 from data.sec.gov.
# www.sec.gov = 200 OK confirmed. submissions/XBRL 은 data.sec.gov 유지.
_WWW_BASE = "https://www.sec.gov"
_SESSION = requests.Session()
_LAST_CALL = 0.0
_MIN_INTERVAL = 0.12  # 10req/sec → ~0.1s



# ── EDGAR display_names 파서 (2026-08-07) ────────────────────────────
# 전문검색 API 가 tickers 를 비워 보내는 경우가 있어 표시명에서 뽑는다.
#   "ESAB Corp  (ESAB)  (CIK 0001877322)" → ("ESAB", "0001877322")
#   "ALEXANDER TECH CORP  (CIK 0001347491)" → (None, "0001347491")  ← 티커 없는 발행사
_DISPLAY_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,5})\)")
_DISPLAY_CIK = re.compile(r"\(CIK\s*(\d{6,10})\)")


def _ticker_from_display(display: str) -> str:
    """표시명에서 티커 추출. CIK 괄호는 제외한다(숫자라 티커 패턴에 안 걸리지만 명시)."""
    for m in _DISPLAY_TICKER.finditer(display or ""):
        cand = m.group(1)
        if cand != "CIK":
            return cand
    return ""


def _cik_from_display(display: str) -> str:
    m = _DISPLAY_CIK.search(display or "")
    return m.group(1) if m else ""


def _headers(user_agent: str) -> dict:
    return {"User-Agent": user_agent, "Accept": "application/json"}


def _throttle():
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()


def _resolve_cik(ticker: str, user_agent: str) -> Optional[str]:
    """티커 → CIK 10자리 (SEC company_tickers.json 매핑)."""
    _throttle()
    try:
        r = _SESSION.get(f"{_WWW_BASE}/files/company_tickers.json",
                         headers=_headers(user_agent), timeout=10)
        r.raise_for_status()
        data = r.json()
        for _, entry in data.items():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry.get("cik_str", ""))
                return cik.zfill(10)
        return None
    except Exception as e:
        logger.warning("SEC CIK resolve failed for %s: %s", ticker, e)
        return None


def get_recent_filings(ticker: str, user_agent: str,
                       form_types: Optional[List[str]] = None) -> List[Dict]:
    """최근 공시 목록 (10-K, 10-Q, 8-K 등)."""
    if not user_agent:
        return []
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]

    cik = _resolve_cik(ticker, user_agent)
    if not cik:
        return []

    _throttle()
    try:
        url = f"{_DATA_BASE}/submissions/CIK{cik}.json"
        r = _SESSION.get(url, headers=_headers(user_agent), timeout=12)
        r.raise_for_status()
        data = r.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        descriptions = recent.get("primaryDocDescription", [])
        accessions = recent.get("accessionNumber", [])

        results = []
        for i, form in enumerate(forms):
            if form in form_types:
                acc = accessions[i].replace("-", "") if i < len(accessions) else ""
                results.append({
                    "form_type": form,
                    "filed_date": dates[i] if i < len(dates) else "",
                    "description": descriptions[i] if i < len(descriptions) else form,
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=5" if not acc else f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/",
                })
            if len(results) >= 10:
                break
        return results
    except Exception as e:
        logger.warning("SEC filings failed for %s: %s", ticker, e)
        return []


def get_insider_transactions(ticker: str, user_agent: str) -> List[Dict]:
    """최근 내부자 거래 (Form 4) — EDGAR full-text search."""
    if not user_agent:
        return []

    _throttle()
    try:
        url = f"{_BASE}/search-index"
        params = {
            "q": f'"{ticker}"',
            "forms": "4",
            "dateRange": "custom",
            "startdt": (time.strftime("%Y-%m-%d", time.gmtime(time.time() - 90 * 86400))),
            "enddt": time.strftime("%Y-%m-%d"),
        }
        r = _SESSION.get(url, params=params, headers=_headers(user_agent), timeout=12)
        r.raise_for_status()
        data = r.json()

        hits = data.get("hits", {}).get("hits", [])
        results = []
        for hit in hits[:10]:
            src = hit.get("_source", {})
            results.append({
                "filer": src.get("display_names", [""])[0] if src.get("display_names") else "",
                "filed_date": src.get("file_date", ""),
                "form_type": "4",
                "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id', '')}/{src.get('file_num', '')}",
            })
        return results
    except Exception as e:
        logger.warning("SEC insider tx failed for %s: %s", ticker, e)
        return []


def _coherent_operands(us_gaap, groups, *, instant, required_context=None):
    """Choose operands only from the latest observed common reporting context.

    All alternatives are considered before selection. A deprecated concept's
    old nonzero value must not win over a current alternative. Missing operands
    are not reported zeroes; no fallback to an older complete period is allowed.
    """
    candidates = []
    for alternatives in groups:
        rows = []
        for concept in alternatives:
            for row in (us_gaap.get(concept, {}).get("units", {}).get("USD", []) or []):
                if not isinstance(row, dict) or row.get("form") not in ("10-K", "10-K/A"):
                    continue
                value = row.get("val")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    continue
                try:
                    end, filed = date.fromisoformat(row["end"]), date.fromisoformat(row["filed"])
                    if filed < end or not isinstance(row.get("accn"), str) or not row["accn"]:
                        continue
                    if instant:
                        if row.get("start"):
                            continue
                    elif not 350 <= (end - date.fromisoformat(row["start"])).days <= 380:
                        continue
                except (KeyError, TypeError, ValueError):
                    continue
                rows.append((concept, row))
        candidates.append(rows)
    all_rows = [row for rows in candidates for _, row in rows]
    if not all_rows:
        return None, {"reason": "no_eligible_annual_operands", "candidate_counts": [len(r) for r in candidates]}
    latest = max(all_rows, key=lambda row: (row["end"], row["filed"], row["accn"]))
    context = required_context or (latest["end"], latest["accn"], None if instant else latest["start"])
    selected = []
    for rows in candidates:
        matches = [(concept, row) for concept, row in rows
                   if (row["end"], row["accn"], None if instant else row["start"]) == context]
        if not matches:
            return None, {"reason": "no_same_period_disclosure_operands",
                          "end": context[0], "document_id": context[1],
                          "candidate_counts": [len(r) for r in candidates]}
        # Prefer the first declared equivalent concept, but reject conflicting
        # duplicate rows within that concept/context instead of relying on order.
        concept = matches[0][0]
        same = [row for tag, row in matches if tag == concept]
        if len({row["val"] for row in same}) > 1:
            return None, {"reason": "conflicting_operand_values", "concept": concept,
                          "end": context[0], "document_id": context[1]}
        selected.append((concept, same[0]))
    return selected, None


def _coherent_debt_operands(us_gaap):
    """Use explicit, non-overlapping debt bundles; current debt is not an alias.

    Anchor every bundle to the latest available debt/equity context so an old
    complete definition cannot beat a newer incomplete definition.
    """
    groups = [("LongTermDebt", "LongTermDebtNoncurrent"),
              ("ShortTermBorrowings", "DebtCurrent"), ("StockholdersEquity",)]
    anchor, rejection = _coherent_operands(us_gaap, groups, instant=True)
    if anchor:
        context = (anchor[0][1]["end"], anchor[0][1]["accn"], None)
    elif rejection.get("end") and rejection.get("document_id"):
        context = (rejection["end"], rejection["document_id"], None)
    else:
        return None, None, rejection
    definitions = (
        ("long_term_plus_short_borrowings_over_equity",
         [("LongTermDebt", "LongTermDebtNoncurrent"), ("ShortTermBorrowings",), ("StockholdersEquity",)]),
        ("noncurrent_plus_current_debt_over_equity",
         [("LongTermDebtNoncurrent",), ("DebtCurrent",), ("StockholdersEquity",)]),
    )
    failures = {}
    for definition, operands in definitions:
        rows, failure = _coherent_operands(us_gaap, operands, instant=True, required_context=context)
        if rows:
            return rows, definition, None
        failures[definition] = failure
    return None, None, {"reason": "no_coherent_debt_bundle", "end": context[0],
                        "document_id": context[1], "bundles": failures}


def get_financial_facts(ticker: str, user_agent: str) -> Dict:
    """XBRL 핵심 재무 데이터 추출 (Brain용 FCF, 순이익, 부채 등)."""
    result = {
        "fcf": None, "net_income": None, "total_debt": None,
        "total_equity": None, "debt_ratio": None,
        "revenue": None, "operating_income": None,
    }
    if not user_agent:
        return result

    cik = _resolve_cik(ticker, user_agent)
    if not cik:
        return result

    _throttle()
    try:
        url = f"{_DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        r = _SESSION.get(url, headers=_headers(user_agent), timeout=15)
        r.raise_for_status()
        data = r.json()

        facts = data.get("facts", {})
        us_gaap = facts.get("us-gaap", {})

        selected_rows = {}

        def _latest_annual(concept: str) -> Optional[float]:
            entry = us_gaap.get(concept, {})
            units = entry.get("units", {})
            usd = units.get("USD", [])
            annuals = [u for u in usd if u.get("form") in ("10-K", "10-K/A")]
            if not annuals:
                return None
            annuals.sort(key=lambda x: x.get("end", ""), reverse=True)
            selected_rows[concept] = dict(annuals[0])
            val = annuals[0].get("val")
            return float(val) if val is not None else None

        result["net_income"] = _latest_annual("NetIncomeLoss")
        result["revenue"] = _latest_annual("Revenues") or _latest_annual("RevenueFromContractWithCustomerExcludingAssessedTax")
        result["operating_income"] = _latest_annual("OperatingIncomeLoss")

        rejections = result["_source_rejections"] = {}
        def coherent(field, groups, *, instant):
            response_cik = str(data.get("cik", ""))
            if not response_cik.isdigit() or response_cik.zfill(10) != str(cik).zfill(10):
                rejections[field] = {"reason": "issuer_identity_missing_or_mismatch"}
                return None
            chosen, rejection = _coherent_operands(us_gaap, groups, instant=instant)
            if rejection:
                rejections[field] = rejection
                return None
            for tag, row in chosen:
                selected_rows[tag] = dict(row)
            return chosen

        fcf_rows = coherent("fcf", [("NetCashProvidedByUsedInOperatingActivities",),
                                   ("PaymentsToAcquirePropertyPlantAndEquipment",)], instant=False)
        if fcf_rows:
            result["fcf"] = float(fcf_rows[0][1]["val"]) - float(fcf_rows[1][1]["val"])

        debt_rows, debt_definition, debt_rejection = _coherent_debt_operands(us_gaap)
        response_cik = str(data.get("cik", ""))
        if not response_cik.isdigit() or response_cik.zfill(10) != str(cik).zfill(10):
            debt_rows, debt_definition = None, None
            debt_rejection = {"reason": "issuer_identity_missing_or_mismatch"}
        if debt_rejection:
            rejections["debt_ratio"] = debt_rejection
        elif debt_rows:
            for tag, row in debt_rows:
                selected_rows[tag] = dict(row)
        equity = _latest_annual("StockholdersEquity")
        if equity is not None:
            result["total_equity"] = equity
        if debt_rows:
            result["total_debt"] = float(debt_rows[0][1]["val"]) + float(debt_rows[1][1]["val"])
            equity = float(debt_rows[2][1]["val"])
            result["total_equity"] = equity
            selected_rows["StockholdersEquity"] = dict(debt_rows[2][1])
            if equity > 0:
                result["debt_ratio"] = round(result["total_debt"] / equity * 100, 1)
            else:
                rejections["debt_ratio"] = {"reason": "nonpositive_equity_denominator"}

        # 2026-07-24 US 재무 확장 (2차 산식 감사: Altman/graham US 결측 해소). Assets/유동자산·부채·이익잉여금
        # 추가 → Altman X1(운전자본/총자산)·X2(이익잉여금/총자산)·graham 유동비율(200%) US 활성화.
        # XBRL 태그 실 SEC 호출 검증(AAPL). 통화=USD(비율이라 currency 상쇄, KR KRW 와 무관).
        result["total_assets"] = _latest_annual("Assets")
        result["retained_earnings"] = _latest_annual("RetainedEarningsAccumulatedDeficit")
        result.update(current_assets=None, current_liabilities=None, working_capital=None, current_ratio=None)
        current_rows = coherent("current_ratio", [("AssetsCurrent",), ("LiabilitiesCurrent",)], instant=True)
        if current_rows:
            _ca, _cl = (float(row["val"]) for _, row in current_rows)
            result["current_assets"] = _ca
            result["current_liabilities"] = _cl
            result["working_capital"] = _ca - _cl  # Altman X1 분자
            if _cl > 0:
                result["current_ratio"] = round(_ca / _cl * 100, 1)  # % 스케일 (graham 200 임계·KIS crnt_rate 정합)
            else:
                rejections["current_ratio"] = {"reason": "nonpositive_current_liabilities_denominator"}

        from api.utils.source_alignment import field_evidence, sec_input
        result["_source_identity"] = {"ticker": ticker, "cik": cik,
                                      "response_cik": data.get("cik"),
                                      "ticker_basis": "SEC company_tickers mapping",
                                      "source": "SEC companyfacts"}
        evidence = result["_source_evidence"] = {}
        def _evidence(field, concepts, definition, unit, instant=False):
            evidence[field] = field_evidence(
                result.get(field), source="SEC", ticker=ticker, issuer_id=cik,
                definition=definition, unit=unit,
                inputs=[sec_input(selected_rows[c], ticker=ticker, cik=data.get("cik"),
                                  concept=c, instant=instant) if c in selected_rows else None
                        for c in concepts])
        rev_tag = "Revenues" if selected_rows.get("Revenues", {}).get("val") else "RevenueFromContractWithCustomerExcludingAssessedTax"
        _evidence("net_income", ["NetIncomeLoss"], "annual_net_income", "USD")
        _evidence("revenue", [rev_tag], "annual_revenue", "USD")
        _evidence("operating_income", ["OperatingIncomeLoss"], "annual_operating_income", "USD")
        _evidence("fcf", ["NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"], "annual_operating_cf_minus_ppe_capex", "USD")
        _evidence("debt_ratio", [tag for tag, _ in debt_rows] if debt_rows else
                  ["LongTermDebt", "ShortTermBorrowings", "StockholdersEquity"],
                  debt_definition or "long_term_plus_short_borrowings_over_equity", "percent", True)
        _evidence("current_ratio", ["AssetsCurrent", "LiabilitiesCurrent"], "current_assets_over_current_liabilities", "percent", True)
        for field, concept in (("total_assets", "Assets"), ("total_equity", "StockholdersEquity"),
                               ("retained_earnings", "RetainedEarningsAccumulatedDeficit"),
                               ("current_assets", "AssetsCurrent"), ("current_liabilities", "LiabilitiesCurrent")):
            if field in result:
                _evidence(field, [concept], "instant_" + field, "USD", True)

        # 2026-06-16 — 부동산 앵커 (XBRL 구조화 장부가, 10-K Item 2 narrative 보완).
        # KR DART 투자부동산과 대칭. REIT 는 RealEstateInvestmentPropertyNet 사용.
        ppe = _latest_annual("PropertyPlantAndEquipmentNet")
        # 2026-06-17 fix: Net(감가상각 차감) 우선, 부재 시 AtCost(gross) — basis 명시(라벨 오인 방지).
        rei_net = _latest_annual("RealEstateInvestmentPropertyNet")
        rei_cost = _latest_annual("RealEstateInvestmentPropertyAtCost")
        rei = rei_net if rei_net is not None else rei_cost
        rei_basis = "net" if rei_net is not None else ("at_cost" if rei_cost is not None else None)
        rou = _latest_annual("OperatingLeaseRightOfUseAsset")
        if any(v is not None for v in (ppe, rei, rou)):
            result["real_estate"] = {
                "ppe_net_usd": ppe,
                "real_estate_investment_usd": rei,
                "real_estate_investment_basis": rei_basis,  # net(감가차감) | at_cost(취득원가)
                "operating_lease_rou_usd": rou,
                "source": "SEC XBRL companyfacts (us-gaap)",
            }

        return result
    except Exception as e:
        logger.warning("SEC financial facts failed for %s: %s", ticker, e)
        return result


def fetch_10k_properties_section(ticker: str, user_agent: str) -> Dict:
    """
    최신 10-K에서 'Item 2. Properties' 섹션 원문 텍스트 추출.
    LLM 파싱(api.analyzers.properties_parser)의 입력으로 사용.

    반환: {accession, filed_date, primary_doc, url, raw_text, char_count}
    실패 시 빈 dict 또는 error 키.
    """
    if not user_agent:
        return {"error": "missing user_agent"}

    cik = _resolve_cik(ticker, user_agent)
    if not cik:
        return {"error": "cik_not_found"}

    _throttle()
    try:
        sub_url = f"{_DATA_BASE}/submissions/CIK{cik}.json"
        r = _SESSION.get(sub_url, headers=_headers(user_agent), timeout=12)
        r.raise_for_status()
        recent = r.json().get("filings", {}).get("recent", {})
    except Exception as e:
        logger.warning("SEC submissions failed for %s: %s", ticker, e)
        return {"error": f"submissions:{e}"}

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    prims = recent.get("primaryDocument", [])

    idx = next((i for i, f in enumerate(forms) if f in ("10-K", "10-K/A")), None)
    if idx is None:
        return {"error": "no_10k"}

    accession = accs[idx]
    filed_date = dates[idx]
    primary = prims[idx] if idx < len(prims) else ""
    acc_no_dash = accession.replace("-", "")
    cik_int = cik.lstrip("0") or cik
    doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dash}/{primary}"

    _throttle()
    try:
        r = _SESSION.get(doc_url, headers={"User-Agent": user_agent}, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.warning("SEC 10-K doc fetch failed for %s: %s", ticker, e)
        return {"error": f"doc_fetch:{e}", "accession": accession, "url": doc_url}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception as e:
        logger.warning("10-K parse failed for %s: %s", ticker, e)
        return {"error": f"parse:{e}", "accession": accession}

    import re
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # "Item 2" ~ "Item 3" 사이 슬라이스 (다양한 포맷 대응)
    patterns = [
        r"(?is)item\s*[\u00a0\s]*2[\.\s]+properties\b(.*?)(?=item\s*[\u00a0\s]*3[\.\s]+legal\s+proceedings|item\s*[\u00a0\s]*3[\.\s]+legal|item\s*[\u00a0\s]*4[\.\s])",
        r"(?is)item\s*2\s*:\s*properties\b(.*?)(?=item\s*3)",
    ]
    section = ""
    for pat in patterns:
        matches = re.findall(pat, cleaned)
        if matches:
            # 10-K는 TOC와 본문에 두 번 나타남 → 긴 쪽이 본문
            section = max(matches, key=len).strip()
            if len(section) > 400:
                break

    if not section or len(section) < 200:
        return {
            "error": "section_not_found",
            "accession": accession, "filed_date": filed_date,
            "url": doc_url, "char_count": 0, "raw_text": "",
        }

    MAX_CHARS = 40000
    if len(section) > MAX_CHARS:
        section = section[:MAX_CHARS]

    return {
        "accession": accession,
        "filed_date": filed_date,
        "primary_doc": primary,
        "url": doc_url,
        "raw_text": section,
        "char_count": len(section),
    }


def scan_risk_filings(
    keywords: List[str],
    user_agent: str,
    forms: str = "8-K,8-K/A",
    days_back: int = 7,
    max_results: int = 50,
) -> Dict:
    """EFTS 키워드 검색으로 리스크 8-K/공시 탐지.

    시장 전체를 대상으로 리스크 키워드가 포함된 공시를 찾아낸다.
    종목별이 아닌 키워드별 스캔이므로 STEP 2.x (매크로 레벨)에서 호출.
    """
    if not user_agent or not keywords:
        return {"ok": False, "filings": [], "error": "missing user_agent or keywords"}

    start_dt = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days_back * 86400))
    end_dt = time.strftime("%Y-%m-%d")

    all_filings = []
    seen_urls = set()

    for keyword in keywords:
        _throttle()
        try:
            params = {
                "q": f'"{keyword}"',
                "forms": forms,
                "dateRange": "custom",
                "startdt": start_dt,
                "enddt": end_dt,
            }
            r = _SESSION.get(
                f"{_BASE}/search-index",
                params=params,
                headers=_headers(user_agent),
                timeout=12,
            )
            r.raise_for_status()
            data = r.json()

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:10]:
                src = hit.get("_source", {})
                names = src.get("display_names") or []
                tickers = src.get("tickers") or []
                display = names[0] if names else ""

                # 🚨 2026-08-07 — 티커 추출 결함 수리.
                #   `src["tickers"]` 가 비어 오는데 그대로 "" 를 넣어, 하류에서
                #   `if ft and ft in port_tickers` 매칭이 **원천 불가**였다(실측 10/10 공백).
                #   결과: sec_risk_flags 가 0/39, SEC 8-K 리스크 downgrade 규칙이 상시 사문화.
                #   티커는 display_names 안에 있다 — "ESAB Corp  (ESAB)  (CIK 0001877322)".
                ticker = tickers[0] if tickers else ""
                if not ticker:
                    ticker = _ticker_from_display(display)
                cik = _cik_from_display(display) or (src.get("ciks") or [""])[0]

                # URL 도 깨져 있었다 — entity_id 는 빈 문자열, file_num 은 **리스트**라
                #   ".../data//['0001877322-26-...']" 가 생성됐다. 사용 가능한 값일 때만
                #   그 경로를 쓰고, 아니면 CIK 기반 EDGAR 조회 링크로 폴백한다.
                entity_id = src.get("entity_id") or ""
                file_num = src.get("file_num")
                if entity_id and isinstance(file_num, str) and file_num:
                    url = f"https://www.sec.gov/Archives/edgar/data/{entity_id}/{file_num}"
                    url_kind = "archive"
                elif cik:
                    url = ("https://www.sec.gov/cgi-bin/browse-edgar"
                           f"?action=getcompany&CIK={cik}&type={forms.split(',')[0]}")
                    url_kind = "cik_browse"
                else:
                    url = "https://www.sec.gov/edgar/search/"
                    url_kind = "search_root"
                dedupe_key = f"{display}|{src.get('file_date','')}|{keyword}"
                if dedupe_key in seen_urls:
                    continue
                seen_urls.add(dedupe_key)

                all_filings.append({
                    "keyword_matched": keyword,
                    "company": display,
                    "ticker": ticker,
                    "cik": cik,
                    "filed_date": src.get("file_date", ""),
                    "form_type": src.get("form_type", forms.split(",")[0]),
                    "description": src.get("display_description", ""),
                    "url": url,
                    "url_kind": url_kind,   # 어느 경로로 만들었는지 관측 (archive 가 정상)
                })
        except Exception as e:
            logger.warning("SEC risk scan failed for keyword '%s': %s", keyword, e)

    all_filings.sort(key=lambda x: x.get("filed_date", ""), reverse=True)
    all_filings = all_filings[:max_results]

    return {
        "ok": len(all_filings) > 0,
        "count": len(all_filings),
        "keywords_scanned": len(keywords),
        "date_range": f"{start_dt} ~ {end_dt}",
        "filings": all_filings,
    }
