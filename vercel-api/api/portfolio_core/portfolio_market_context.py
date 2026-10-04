"""Closed, public-only market context projection for portfolio analysis."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import ipaddress
import json
import re
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit

from .portfolio_public_sources import (
    safe_public_text, _finite_number, _EMAIL_RE, _PHONE_RE, _UUID_RE, _JWT_RE,
    _SECRET_KEY_RE, _SECRET_RE, _PATH_RE, _URL_IN_TEXT_RE, _HTML_RE,
)

SCHEMA = "alphaconsole-market-context-v1"
MACRO_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
ECOS_POLICY_SERIES = {"stat_code": "722Y001", "item_code": "0101000", "frequency": "M",
                      "series_id": "ECOS/722Y001/0101000", "source_url": "https://ecos.bok.or.kr/"}
NEWS_FEEDS = ("headlines", "bloomberg_google_headlines", "us_headlines")
MARKET_SPECS = {"usd_krw": ("fx", "USD/KRW"), "usd_jpy": ("fx", "USD/JPY"), "eur_usd": ("fx", "EUR/USD"),
                "wti_oil": ("commodity", "WTI 원유"), "copper": ("commodity", "구리"),
                "gold": ("commodity", "금"), "silver": ("commodity", "은"),
                "brent": ("commodity", "브렌트 원유"), "natural_gas": ("commodity", "천연가스"),
                "corn": ("commodity", "옥수수"), "wheat": ("commodity", "밀"),
                "soybean": ("commodity", "대두"), "coffee": ("commodity", "커피"),
                "sugar": ("commodity", "설탕"), "cotton": ("commodity", "면화")}
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_NAIVE_KST = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\Z", re.ASCII)
_CALENDAR_SCHEDULE_SOURCES = {
    "ISM": ("미국", "https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/"),
    "UMich": ("미국", "https://data.sca.isr.umich.edu/survey-info.php"),
    "Fed": ("미국", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    "ECB": ("유럽", "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"),
    "BOJ": ("일본", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"),
    "BOK": ("한국", "https://www.bok.or.kr/portal/main/contents.do?menuNo=200755"),
}

# These recognize words in a filing, not economic exposure or price direction.
# Generic exchange-rate/crude-oil references use a clearly qualified benchmark.
_FILING_TERMS = {
    "usd_krw": re.compile(r"환율"),
    "usd_jpy": re.compile(r"USD/JPY|달러[ /·ㆍ-]엔"),
    "eur_usd": re.compile(r"EUR/USD|유로[ /·ㆍ-]달러"),
    "wti_oil": re.compile(r"(?<![가-힣])원유|국제\s*유가|유가\s*(?:변동|상승|하락)|\bWTI\b"),
    "copper": re.compile(r"구리(?!시)|전기동(?!력)|동합금|동스크랩|동박"),
    "gold": re.compile(r"금괴|금\s*\(Gold\)|(?<![가-힣])금[·ㆍ,/]\s*은(?![가-힣])", re.I),
    "silver": re.compile(r"은괴|은\s*\(Silver\)|(?<![가-힣])금[·ㆍ,/]\s*은(?![가-힣])", re.I),
    "brent": re.compile(r"브렌트(?:유)?|\bBrent\b", re.I),
    "natural_gas": re.compile(r"천연가스|\bLNG\b", re.I),
    "corn": re.compile(r"옥수수"),
    "wheat": re.compile(r"소맥|원맥|밀가루|(?<![가-힣])밀(?=[\s(·,]|[을를은는](?:\s|$))"),
    "soybean": re.compile(r"탈지대두|대두유|대두박|(?<![가-힣])대두(?=[\s(·,]|[을를은는](?:\s|$))"),
    "coffee": re.compile(r"생두|커피콩|커피\s*원두|원두커피"),
    "sugar": re.compile(r"원당|설탕"),
    "cotton": re.compile(r"원면|목화|면화"),
}
_ISSUER_ACTIVITY = re.compile(r"당사|우리회사|연결회사|지배기업|종속회사|자회사|회사의")
_OTHER_SUBJECT = re.compile(
    r"(?:경쟁사|타사|업계|고객사|고객|수요처|거래처|납품처|전방산업|공급업체|협력사)(?:는|은|가|이|의|\s)")
_CONTINUED_ISSUER_CLAUSE = re.compile(
    r"\s*(?:주요\s*)?(?:원재료|주원료|원료|제품|상품|원맥|천연가스|탈지대두|생두|원면)(?:의|은|는|이|가|을|를|\s)")
_BLOCKED_ACTIVITY = re.compile(
    r"(?:생산|제조|판매|공급|사용|투입|매입|수입|구매|구입|조달|선물거래|환?헤지|환?헷지).{0,20}"
    r"(?:하지\s*않|없습니다|계획|예정|가정|검토|전망|예상|(?:할|될)?\s*수\s*있)")
_CONDITIONAL_ACTIVITY = re.compile(r"조건부|가정하|전제로|경우에만")
_INDIRECT_COMMODITY = re.compile(r"장비|설비|검사기|운송|운반선|플랫폼|가열로|물류서비스|시추|건조장")
_RISK_MANAGEMENT = re.compile(
    r"(?:가격|환율|금속).{0,30}(?:위험|변동).{0,80}(?:선물거래|환?헤지|환?헷지|리스크.{0,16}관리)|"
    r"(?:선물거래|환?헤지|환?헷지).{0,60}(?:위험|리스크|관리)")
_FX_CONTINUATION = re.compile(
    r"\s*(?:이에\s*따라\s*)?(?:(?:주요\s*)?(?:원재료|주원료|원료|매입단가)(?:의|은|는|이|가|\s)|수입의\s*경우)")
_FX_UNCONFIRMED = re.compile(
    r"무관|관계\s*없|관련\s*없|영향.{0,12}(?:없|받지)|연동되지|"
    r"전망|예상|예정|계획|가정|가능성|(?:할|될)\s*수\s*있")
_POWER_ROLES = {
    "electricity-input": ("power-use", "전력 구매·사용"),
    "electricity-supply": ("power-supply", "발전·전력 공급"),
    "electricity-equipment": ("power-equipment", "전력설비 생산·공급"),
}
_POWER_CABLE = r"(?:전력(?:\s*및\s*절연)?케이블|초고압\s*케이블|전력선)"
_POWER_TERMS = re.compile(r"전력|(?<![가-힣])전기(?=요금|료|를|의|\s)|발전|변압기|차단기|송전|배전|" + _POWER_CABLE)
# A bounded locative/source noun may intervene before the purchase verb. Do
# not cross another activity clause or borrow a different product's sale.
_POWER_PURCHASE_SOURCE = (
    r"(?:(?:(?!(?:생산|제조|판매|공급|사용)(?:하는|한|할|하여|하고)|받는|받아)"
    r"[가-힣A-Za-z0-9·]){1,40}(?:에서|(?:으)?로부터)\s*)?")
_POWER_RECIPIENT = r"(?:(?:일반|국내|해외)\s*)?(?:고객|수요처|거래처)(?:에게|에)\s*"
_POWER_UNCONFIRMED = re.compile(
    r"않|아니|없|중단|제외|종료|폐지|전망|예상|예정|계획|가정|검토|추진|가능성|조건부|"
    r"조건.{0,24}(?:면|경우)|(?<![가-힣])[가-힣]+(?:으면|되면|하면|라면|다면|이면)(?=\s|[,.;])|"
    r"(?:할|될)\s*수\s*있|과거|전년도|만약|예를\s*들어|예시|예문|인용|문구|[\"'“”‘’]")
_INFRASTRUCTURE_ROLES = {"port-operation": "항만·터미널 운영"}
_PORT_OPERATION = re.compile(
    r"(?P<term>항만\s*터미널|컨테이너\s*터미널|항만|부두)(?:을|를)\s*"
    r"운영(?:합니다|하고\s*있(?:습니다|으며)|하였습니다|했습니다|하며|"
    r"하는\s*(?:항만하역\s*)?사업(?:을\s*영위|과))")
_INFRASTRUCTURE_UNCONFIRMED = re.compile(
    r"않|아니|없|중단|제외|종료|폐지|전망|예상|예정|계획|가정|검토|추진|가능성|조건부|"
    r"조건.{0,24}(?:면|경우)|(?<![가-힣])[가-힣]+(?:으면|되면|하면|라면|다면|이면)(?=\s|[,.;])|"
    r"(?:할|될)\s*수\s*있|과거|전년도|만약|예를\s*들어|"
    r"예시|예문|인용|문구|[\"'“”‘’]")


def index_filing_power_context(business):
    """Reported operating roles, not a power price or inferred value chain.

    Reuse only the sanitized, issuer-bound public excerpt. An industry's power
    needs never establish an issuer channel; different filings are not one event.
    """
    index = {key: [] for key in _POWER_ROLES}
    for row in business["rows"]:
        title = re.fullmatch(r"(?:\[(?:기재정정|첨부정정|정정)\]\s*)?사업보고서\s*\(([0-9]{4})\.(0[1-9]|1[0-2])\)",
                             row["source"]["report_name"])
        filed = row["source"]["as_of"]
        if (not title or title[1] != row["fiscal_year"]
                or row["source"]["receipt_no"][:8] != filed.replace("-", "")
                or filed > date.today().isoformat()):
            continue
        found = {}
        sentences = [part.strip() for start, end in _sentence_spans(row["text"])
                     for part in re.split(r"[●■•]", row["text"][start:end])]
        for sentence in sentences:
            term = next((match for match in _POWER_TERMS.finditer(sentence)
                         if _issuer_bound(sentence, sentence, match.group(), row.get("name", ""),
                                          term_position=match.start())), None)
            if (not term or not sentence.endswith((".", "。", "!"))
                    or _POWER_UNCONFIRMED.search(sentence)
                    or _OTHER_SUBJECT.search(sentence)):
                continue
            # Match the actual object/activity, not a sentence-wide pair of
            # words (e.g. a manufacturer supplying electricity-producing gear).
            patterns = {
                "electricity-input": (
                    r"(?<![가-힣])(?:전력|전기)(?:을|를)?\s*" + _POWER_PURCHASE_SOURCE + r"(?:구매|구입|매입|사용|소비)"
                    r"(?:합니다|하였습니다|했습니다|하고\s*있|하여|하며|하였|했|해\s*왔)|"
                    r"(?:전기요금|전력요금|전기료).{0,25}(?:부담|비용|원가|지급)|"
                    r"(?:비용|원가).{0,25}(?:전기요금|전력요금|전기료)"),
                "electricity-supply": (
                    r"(?<![가-힣])(?:전력|전기)(?:을|를)?\s*(?:생산|판매|공급)"
                    r"(?:합니다|하였습니다|했습니다|하고\s*있|하여|하며|하였|했|업|\s*사업|\s*수익)|"
                    r"(?<![가-힣])(?:전력|전기)(?:을|를)\s*" + _POWER_PURCHASE_SOURCE
                    + r"(?:구매|구입|매입)하여\s*" + _POWER_RECIPIENT
                    + r"판매(?:합니다|하고\s*있습니다|하고\s*있으며|하였습니다)|"
                    r"(?<![가-힣])(?:전력|전기)(?:을|를)\s*" + _POWER_RECIPIENT
                    + r"(?:판매|공급)(?:합니다|하고\s*있습니다|하고\s*있으며|하였습니다)|"
                    r"발전\s*사업(?:을|의)?\s*(?:영위|운영)|발전소(?:를|을)?\s*운영"),
                "electricity-equipment": (
                    r"(?:변압기|차단기|전력\s*기기|전력\s*설비|송전\s*설비|배전\s*설비|분전반|배전반|송배전용\s*케이블)"
                    r"(?:(?!사용|설치|구입|구매|운영).){0,80}(?:생산|제조|판매|공급)"
                    r"(?:합니다|하고|하는|하여|하며|하였|했|\s*(?:및|판매|중)|을\s*주된\s*사업으로\s*영위)|"
                    r"(?:생산|제조|판매)(?:\s*및\s*(?:생산|제조|판매))?\s*중인\s*(?:주요\s*)?제품"
                    r".{0,60}(?:변압기|차단기|전력\s*기기|전력\s*설비)|"
                    r"(?:생산|제조|판매|공급)(?:하는|한)?\s*(?:변압기|차단기|전력\s*기기|전력\s*설비)|"
                    r"전력공급\s*과정.{0,100}전기전자기기.{0,40}(?:제작|생산|제조|판매|공급)|"
                    r"(?:송전|배전|송배전|송[·ㆍ/]배전).{0,20}(?:공사|설비)"
                    r"(?:를|을)?\s*(?:시공|건설|공급)|"
                    + _POWER_CABLE + r"(?:을|를)\s*(?:주력으로\s*(?:각종\s*)?전선류(?:을|를)\s*)?"
                    r"(?:생산|제조|판매|공급)(?:\s*및\s*(?:생산|제조|판매|공급))?"
                    r"(?:합니다|하고\s*있|하여|하며|하였습니다)|"
                    r"주요\s*생산\s*및\s*판매\s*품목(?:은|는)\s*" + _POWER_CABLE
                    + r"(?:\s*등\s*전력선)?(?:\s*[,·ㆍ]\s*[가-힣A-Za-z0-9 -]{1,35}){0,6}"
                    r"\s*(?:등)?입니다\."),
            }
            for role, pattern in patterns.items():
                if re.search(pattern, sentence):
                    found.setdefault(role, (term.group(), sentence))
        for role, (term, quote) in found.items():
            index[role].append({"company_id": row["issuer_id"], "term": term,
                "excerpt": row["text"], "url": row["source"]["url"],
                "as_of": row["source"]["as_of"], "source": row["source"]["report_name"],
                "fiscal_year": row["fiscal_year"], "truncated": row["truncated"],
                "channels": [{"kind": _POWER_ROLES[role][0], "quote": quote}]})
    return {"by_role": index, "coverage": {**business["coverage"],
        "matched_issuers": len({ref["company_id"] for refs in index.values() for ref in refs}),
        "references": sum(map(len, index.values()))}}


def index_filing_infrastructure_context(business):
    """Reported issuer port operation, not a concession benefit or current right."""
    index = {key: [] for key in _INFRASTRUCTURE_ROLES}
    for row in business["rows"]:
        title = re.fullmatch(r"(?:\[(?:기재정정|첨부정정|정정)\]\s*)?사업보고서\s*\(([0-9]{4})\.(0[1-9]|1[0-2])\)",
                             row["source"]["report_name"])
        filed = row["source"]["as_of"]
        if not title or title[1] != row["fiscal_year"] or filed > date.today().isoformat():
            continue
        found = None
        # Public excerpts can join the next Latin-named business section
        # directly after a period (for example ``있습니다.W&D``). Keep this
        # boundary local so established power/FX/commodity quoting is unchanged.
        sentences = re.split(r"(?<=[.!。])(?=\s|[A-Z가-힣]|$)", row["text"])
        for sentence in (part.strip() for part in sentences):
            operation = _PORT_OPERATION.search(sentence)
            if not operation or _INFRASTRUCTURE_UNCONFIRMED.search(sentence):
                continue
            own_subjects = list(_ISSUER_ACTIVITY.finditer(sentence[:operation.start("term")]))
            issuer_name = row.get("name", "")
            if issuer_name:
                own_name = re.compile(
                    rf"(?<![가-힣A-Za-z0-9]){re.escape(issuer_name)}(?:은|는|이|가|의)(?=\s|$)")
                own_subjects.extend(own_name.finditer(sentence[:operation.start("term")]))
            if not own_subjects:
                continue
            quote = sentence[max(match.start() for match in own_subjects):].strip()
            bound_operation = _PORT_OPERATION.search(quote)
            if (not bound_operation or not quote.endswith((".", "。", "!"))
                    or _INFRASTRUCTURE_UNCONFIRMED.search(quote)
                    or _OTHER_SUBJECT.search(quote)
                    or not _issuer_bound(quote, quote, bound_operation.group("term"), issuer_name,
                                         term_position=bound_operation.start("term"))):
                continue
            found = (bound_operation.group("term"), quote)
            break
        if found:
            term, quote = found
            index["port-operation"].append({"company_id": row["issuer_id"], "term": term,
                "excerpt": row["text"], "url": row["source"]["url"],
                "as_of": row["source"]["as_of"], "source": row["source"]["report_name"],
                "fiscal_year": row["fiscal_year"], "truncated": row["truncated"],
                "channels": [{"kind": "port-operation", "quote": quote}]})
    return {"by_role": index, "coverage": {**business["coverage"],
        "matched_issuers": len({ref["company_id"] for refs in index.values() for ref in refs}),
        "references": sum(map(len, index.values()))}}


def _sentence_spans(text):
    spans, start = [], 0
    for boundary in re.finditer(r"(?<![0-9])\.(?![0-9])(?=\s|$|[가-힣\[])|[!?。]", text):
        end = boundary.end()
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            spans.append((left, right))
        start = end
    left, right = start, len(text)
    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    if left < right:
        spans.append((left, right))
    return spans


def _indicator_passages(text, position, fx=False):
    spans = _sentence_spans(text)
    current = next((n for n, (start, end) in enumerate(spans) if start <= position < end), None)
    if current is None:
        return []
    windows = [(current, current)]
    if current:
        windows.append((current - 1, current))
    if fx and current >= 2:
        # Resolve only an explicit input-cost continuation, not arbitrary prior
        # issuer mentions anywhere in the filing (e.g. an industry paragraph).
        middle = text[spans[current - 1][0]:spans[current - 1][1]]
        last = text[spans[current][0]:spans[current][1]]
        if _FX_CONTINUATION.match(middle) and _FX_CONTINUATION.match(last):
            windows.append((current - 2, current))
    passages = []
    for first, last in windows:
        start, end = spans[first][0], spans[last][1]
        quote = text[start:end]
        sentence = text[spans[current][0]:spans[current][1]]
        item = (sentence, quote)
        if len(quote) <= 600 and item not in passages:
            passages.append(item)
    return passages


def _issuer_bound(sentence, quote, term_text, issuer_name="", fx=False, *, term_position=None):
    position = sentence.find(term_text) if term_position is None else term_position
    if position < 0 or sentence[position:position + len(term_text)] != term_text:
        return False
    subjects = [(match.start(), True) for match in _ISSUER_ACTIVITY.finditer(sentence[:position])]
    if issuer_name:
        # Exact public issuer name as a grammatical subject, never a fuzzy
        # company-name hit or an unrelated company mentioned in the same filing.
        own_name = re.compile(rf"(?<![가-힣A-Za-z0-9]){re.escape(issuer_name)}(?:은|는|이|가|의)(?=\s|$)")
        subjects.extend((match.start(), True) for match in own_name.finditer(sentence[:position]))
    subjects.extend((match.start(), False) for match in _OTHER_SUBJECT.finditer(sentence[:position]))
    if subjects:
        return max(subjects)[1]
    if quote == sentence or not (_CONTINUED_ISSUER_CLAUSE.match(sentence)
                                 or (fx and _FX_CONTINUATION.match(sentence))):
        return False
    previous = quote[:-len(sentence)]
    prior_subjects = [(match.start(), True) for match in _ISSUER_ACTIVITY.finditer(previous)]
    if issuer_name:
        prior_subjects.extend((match.start(), True) for match in own_name.finditer(previous))
    prior_subjects.extend((match.start(), False) for match in _OTHER_SUBJECT.finditer(previous))
    return bool(prior_subjects and max(prior_subjects)[1] and not _OTHER_SUBJECT.search(sentence))


def _commodity_roles(sentence, term_text):
    token = re.escape(term_text)
    downstream = bool(re.search(
        rf"(?:고객|고객사|수요처|거래처|납품처)(?:는|은|가|이|의).{{0,80}}{token}|"
        rf"{token}.{{0,60}}(?:생산|제조|사용)하는\s*(?:고객|고객사|수요처|거래처|납품처)", sentence))
    if downstream:
        return False, False
    downstream_input = bool(re.search(
        rf"{token}.{{0,80}}(?:고객|고객사|수요처|거래처|납품처)\s*(?:의\s*)?(?:원재료|주원료)", sentence))
    input_channel = not downstream_input and bool(re.search(
        rf"(?:원재료|주원료|원료).{{0,100}}{token}|"
        rf"{token}.{{0,100}}(?:원재료|주원료|원료|투입|매입|구매|구입|수입|조달)", sentence))
    if re.search(r"(?:직수입|수입|매입|구매).{0,30}제외", sentence) or (
            re.search(r"운송|운반선|건조장", sentence)
            and not re.search(r"(?:원재료|주원료|원료).{0,30}(?:사용|투입)|매입|구매|구입", sentence)):
        input_channel = False
    start = sentence.find(term_text)
    nearby = sentence[max(0, start - 100):start + len(term_text) + 100]
    product_channel = (not _INDIRECT_COMMODITY.search(nearby) and bool(re.search(
        rf"{token}.{{0,100}}(?:생산|제조|판매|공급|제조업체)|"
        rf"(?:생산|제조|판매|공급|제조업체).{{0,100}}{token}", sentence)))
    if input_channel:
        # Making a finished product FROM a material is not selling the material.
        # Keep both roles only when the material itself has a direct sales verb.
        product_channel = product_channel and bool(re.search(
            rf"{token}(?:\([^)]*\))?(?:\s*(?:제품|상품|소재))?\s*(?:을|를|의)\s*(?:직접\s*)?(?:생산|제조|판매|공급)|"
            rf"(?:생산|제조|판매|공급)(?:하는|한)\s*{token}", sentence))
    return input_channel, product_channel


def _fx_product_pricing(sentence, term_text):
    token = re.escape(term_text)
    # A product's INPUT price is not its selling price.
    if re.search(r"수입의\s*경우.{0,40}(?:제품|상품)", sentence):
        return False
    gap = r"(?:(?!원재료|주원료|원료|매입|구매|수입).){0,24}"
    product_price = rf"(?:제품|상품){gap}(?:가격|단가)|(?:가격|단가){gap}(?:제품|상품)"
    return bool(re.search(
        rf"(?:{product_price}).{{0,80}}{token}|{token}.{{0,80}}(?:{product_price})", sentence)
        and re.search(r"영향|따라|기인|연동|변동", sentence))


def _fx_import_input_cost(sentence, token):
    # A disclosed purchase/sourcing statement followed by its import-price
    # qualification is one channel, even across a comma. Exporting products,
    # an import-share number alone, or an industry's FX discussion is not.
    if not sentence.endswith(".") or re.search(r"않|아니|없|중단|제외|검토", sentence):
        return False
    for continuation in re.finditer(r"수입의\s*경우", sentence):
        prefix = sentence[:continuation.start()]
        if not re.search(
                r"(?:원재료|주원료|원료|부재료).{0,140}매입(?:물량|금액|비중).{0,100}"
                r"수입.{0,60}(?:조달|매입|구매)하고\s*(?:있으며|있습니다)", prefix):
            continue
        clause = sentence[continuation.end():]
        if re.search(rf"^[^,;；]{{0,120}}{token}(?:의)?\s*변동에\s*영향을\s*받고\s*있습니다\.$", clause):
            return True
    return False


def _fx_reported_revenue(sentence, effect):
    # Bind the FX effect to the FIRST financial metric, rather than vetoing
    # revenue just because a later list also reports operating/net profit.
    # Conversely, a realized profit verb must not qualify unrelated sales.
    if (not sentence.endswith(".") or re.search(
            r"않|아니|없|중단|예상|전망|예정|계획|가능|가정|여부|검토|"
            r"예시|예문|인용|설명하는|문구|[\"'“”‘’]", sentence)):
        return False
    metrics = re.compile(
        r"매출\s*(?:총이익|이익|원가|채권|대비|비중|비율|구성|목표)|"
        r"영업이익|(?:당기)?순이익|세전이익|영업비용|원재료비|매입원가|비용|원가|매출액|매출")
    realized = r"기록했|기록하였|증가했|감소했|증가하였|감소하였|증가한(?!다)|감소한(?!다)"
    for match in re.finditer(effect, sentence):
        tail = sentence[match.end():]
        metric = metrics.search(tail[:80])
        if metric is not None:
            if metric.group() in ("매출", "매출액"):
                sales_tail = tail[metric.end():]
                # A collective "recorded" predicate can cover a list of
                # actual amounts. A vague revenue clause followed by a profit
                # record cannot borrow that later predicate.
                sales_clause = re.split(r"[,，;；]", sales_tail, maxsplit=1)[0]
                amount_list = re.match(
                    r"\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:조|억|천만|백만|천)?"
                    r"(?:원|달러|유로|엔)\s*[,，]", sales_tail)
                if (re.search(realized, sales_clause) or
                        (amount_list and re.search(r"기록했|기록하였", sales_tail))):
                    return True
            continue
        prior = list(metrics.finditer(sentence[max(0, match.start() - 35):match.start()]))
        if prior and prior[-1].group() in ("매출", "매출액") and re.search(realized, tail):
            return True
    return False


def _fx_channels(sentence, term_text):
    """Quoted business mechanisms, never currency direction or stock returns."""
    if _FX_UNCONFIRMED.search(sentence) or _OTHER_SUBJECT.search(sentence):
        return []
    token = re.escape(term_text)
    kinds = []
    if _fx_product_pricing(sentence, term_text):
        kinds.append("fx-pricing")
    cost = (r"(?:원재료|주원료|원료|부재료).{0,28}(?:가격|단가|비용|원가)|"
            r"(?:매입|구매|수입|조달)\s*(?:가격|단가|비용|원가)")
    for clause in re.split(r"[,;；]", sentence):
        if (re.search(rf"(?:{cost}).{{0,100}}{token}|{token}.{{0,100}}(?:{cost})", clause)
                and re.search(rf"{token}.{{0,60}}(?:영향|따라|기인|연동)|(?:영향|따라).{{0,24}}{token}", clause)):
            kinds.append("fx-input-cost")
            break
    if "fx-input-cost" not in kinds and _fx_import_input_cost(sentence, token):
        kinds.append("fx-input-cost")
    effect = rf"{token}.{{0,16}}(?:영향|효과|변동|상승|하락).{{0,8}}(?:으로|로|따라|기인|인하여)"
    # Require the report to attribute a realized sales figure/change to FX.
    # Foreign-currency presentation and export share alone cannot pass.
    if _fx_reported_revenue(sentence, effect):
        kinds.append("fx-revenue")
    return kinds


def _filing_channels(text, code, pattern, issuer_name=""):
    channels = {}
    for term in pattern.finditer(text):
        is_fx = code in ("usd_krw", "usd_jpy", "eur_usd")
        for sentence, quote in _indicator_passages(text, term.start(), fx=is_fx):
            activity_scope = quote if is_fx else sentence
            if ((is_fx and (not sentence.endswith(".") or _FX_UNCONFIRMED.search(quote)))
                    or (_BLOCKED_ACTIVITY.search(activity_scope) or _CONDITIONAL_ACTIVITY.search(activity_scope))
                    or not _issuer_bound(sentence, quote, term.group(), issuer_name, fx=is_fx)):
                continue
            input_channel, product_channel = ((False, False) if is_fx else
                                              _commodity_roles(sentence, term.group()))
            fx_kinds = _fx_channels(sentence, term.group()) if is_fx else []
            for kind in fx_kinds:
                channels.setdefault(kind, quote)
            if input_channel:
                channels.setdefault("input-cost", quote)
            if product_channel:
                channels.setdefault("product-sales", quote)
            # This only records a disclosed mitigation activity beside an
            # already-grounded channel. It never means the exposure is fully hedged.
            base_channel = ((is_fx and bool(fx_kinds))
                            or (not is_fx and (input_channel or product_channel)))
            if base_channel and _RISK_MANAGEMENT.search(sentence):
                channels.setdefault("risk-management", quote)
    order = (("fx-pricing", "fx-input-cost", "fx-revenue", "risk-management") if code in ("usd_krw", "usd_jpy", "eur_usd")
             else ("input-cost", "product-sales", "risk-management"))
    return [{"kind": kind, "quote": channels[kind]} for kind in order if kind in channels][:4]


def index_filing_market_context(business):
    """Index already-sanitized public filing excerpts, shared across selections."""
    index = {code: [] for code in _FILING_TERMS}
    matched = set()
    for row in business["rows"]:
        for code, pattern in _FILING_TERMS.items():
            term = pattern.search(row["text"])
            if not term or (code == "usd_krw" and not re.search(
                    r"수출|수입|원가|원재료|매출|가격|비용|손익|환리스크", row["text"])):
                continue
            # Korean '원유' also means raw milk. A bare word must not join a
            # dairy producer to oil; require petroleum context or an oil-price term.
            if code == "wti_oil" and term.group() == "원유" and not re.search(
                    r"석유|정유|원유운반|원유수송|원유생산|유조선|LPG|해양|플랜트", row["text"]):
                continue
            if code in ("gold", "silver"):
                # A textbook list of metals in an industry introduction does
                # not describe this issuer's business. Require issuer context.
                sentence_start = max(row["text"].rfind(".", 0, term.start()),
                                     row["text"].rfind("。", 0, term.start())) + 1
                sentence_end = row["text"].find(".", term.end())
                sentence = row["text"][sentence_start:sentence_end if sentence_end >= 0 else None]
                if not re.search(r"당사|종속회사|자회사|주요\s*(?:제품|원재료)", sentence):
                    continue
            if code == "soybean" and term.group() == "대두" and not re.search(
                    r"곡물|원재료|주원료|콩|식품|사료|제분|농산물", row["text"]):
                continue
            channels = _filing_channels(row["text"], code, pattern, row.get("name", ""))
            index[code].append({"company_id": row["issuer_id"], "term": term.group(),
                "excerpt": row["text"], "url": row["source"]["url"],
                "as_of": row["source"]["as_of"], "source": row["source"]["report_name"],
                "fiscal_year": row["fiscal_year"], "truncated": row["truncated"],
                **({"channels": channels} if channels else {})})
            matched.add(row["issuer_id"])
    return {"by_indicator": index, "power": index_filing_power_context(business),
        "infrastructure": index_filing_infrastructure_context(business), "coverage": {**business["coverage"],
        "matched_issuers": len(matched), "references": sum(map(len, index.values()))}}


def _stamp(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _news_date(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    if _NAIVE_KST.fullmatch(value):
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=9)))
            return parsed.isoformat()
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Some preserved feeds use an RFC-style date with a colon in the
        # explicitly supplied numeric offset. Normalize only that syntax;
        # never infer a missing timezone or accept an invalid offset.
        colon_zone = re.fullmatch(
            r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{1,2} "
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
            r"[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} )([+-])([0-9]{2}):([0-9]{2})", value)
        if colon_zone:
            prefix, sign, hours, minutes = colon_zone.groups()
            if int(hours) >= 24 or int(minutes) >= 60:
                return None
            value = prefix + sign + hours + minutes
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return parsed.isoformat() if parsed.tzinfo is not None else None


def _url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password or not parts.hostname.isascii():
            return None
        port = parts.port
        host = parts.hostname.lower()
        if port not in (None, 443) or "." not in host or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        decoded = value
        for _ in range(8):
            unfolded = unquote(decoded, errors="strict")
            if unfolded == decoded:
                break
            decoded = unfolded
        else:
            return None
        if any(ord(c) < 33 or ord(c) == 127 or c in "<>" for c in decoded):
            return None
        if re.search(r"(?:[?&])(?:token|access_token|key|api_key|password|secret|signature|auth)=", decoded, re.I):
            return None
    except (ValueError, UnicodeError):
        return None
    netloc = parts.hostname.lower() + (f":{port}" if port and port != 443 else "")
    result = urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))
    # The shared narrative sanitizer deliberately rejects URLs; validate the
    # URL components as text while keeping the clickable URL in its own field.
    # Long numeric article identifiers are normal in URL paths, not narrative
    # identifiers. Neutralize only those runs for path inspection; never alter
    # the returned URL. Keep the query fully strict, including decoded text.
    try:
        decoded_parts = urlsplit(decoded)
        decoded_path = decoded_parts.path or "/"
        path_sensitive_patterns = (
            _EMAIL_RE, _PHONE_RE, _UUID_RE, _JWT_RE, _SECRET_KEY_RE,
            _SECRET_RE, _PATH_RE, _URL_IN_TEXT_RE, _HTML_RE,
        )
        if any(pattern.search(decoded_path) for pattern in path_sensitive_patterns):
            return None
        checked_path = re.sub(r"[0-9]{10,}", "0", decoded_path, flags=re.ASCII)
        checked_query = decoded_parts.query
        if (safe_public_text(parts.hostname, 253) is None or
                safe_public_text(checked_path, 1800) is None or
                (checked_query and safe_public_text(checked_query, 1800) is None)):
            return None
    except (ValueError, UnicodeError):
        return None
    return result


def _project_release_calendar(macro):
    """Project saved scheduled dates, not verified outcomes or issuer links."""
    counts = {"input": 0, "accepted": 0, "rejected": 0, "omitted": 0, "shape_errors": 0,
              "missing": not isinstance(macro, dict) or "global_events" not in macro,
              "total": 0, "returned": 0}
    if counts["missing"]:
        return [], counts
    rows = macro["global_events"]
    if not isinstance(rows, list):
        counts["shape_errors"] = 1
        return [], counts
    counts["input"] = len(rows)
    collected = macro.get("collected_at")
    # An upcoming schedule is not future-dated market data. Only the collection
    # clock is bounded by now; never replace a missing clock with the schedule.
    if isinstance(collected, str) and _DATE.fullmatch(collected):
        today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        observed = collected if _valid_date(collected) and collected <= today else None
    else:
        observed = _stamp(collected)
        if observed and datetime.fromisoformat(observed.replace("Z", "+00:00")) > datetime.now(timezone.utc):
            observed = None
    if observed is None:
        counts["rejected"] = len(rows)
        return [], counts
    unique, valid = {}, 0
    for row in rows:
        if not isinstance(row, dict):
            counts["rejected"] += 1
            continue
        source = safe_public_text(row.get("source"), 100)
        kind = safe_public_text(row.get("source_kind"), 40)
        name = safe_public_text(row.get("name"), 240)
        country = safe_public_text(row.get("country"), 80)
        scheduled, release_id = row.get("date"), row.get("release_id")
        url = _url(row.get("source_url"))
        if (not all((source, kind, name, country, url))
                or any(row.get(key) != value for key, value in (
                    ("source", source), ("source_kind", kind), ("name", name),
                    ("country", country), ("source_url", url)))
                or not isinstance(scheduled, str) or not _DATE.fullmatch(scheduled)
                or not _valid_date(scheduled)):
            counts["rejected"] += 1
            continue
        if source == "FRED":
            bound = (kind == "release" and country == "미국"
                     and isinstance(release_id, int) and not isinstance(release_id, bool)
                     and 0 < release_id <= 1_000_000
                     and url == f"https://fred.stlouisfed.org/release?rid={release_id}")
        else:
            bound = (kind == "schedule" and release_id is None
                     and _CALENDAR_SCHEDULE_SOURCES.get(source) == (country, url))
        if not bound:
            counts["rejected"] += 1
            continue
        key = json.dumps([source, kind, url, name, scheduled, country, release_id],
                         ensure_ascii=False, separators=(",", ":"))
        try:
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        except UnicodeError:
            counts["rejected"] += 1
            continue
        valid += 1
        # Keep only the closed output fields; collector templates and arbitrary
        # private metadata cannot become evidence, strength or company edges.
        unique.setdefault(key, {"id": "market:release-calendar:" + digest,
            "kind": "release-calendar", "title": name, "summary": "발표 예정 · " + country,
            "source": source, "url": url, "as_of": scheduled, "observed_at": observed,
            "value": None, "change_pct": None, "unit": None, "company_ids": [],
            "basis": "market-context", "schedule": {"country": country, "source_kind": kind,
                                                     "release_id": release_id},
            "verified_common_event": False,
            "reason": "공개 일정 자료의 예정일이에요. 일정 변경 가능성이 있으며 발표 결과·정책 결정·종목별 영향은 확인하지 않았어요."})
    chosen = sorted(unique.values(), key=lambda row: (row["as_of"], row["title"], row["url"]))[:12]
    counts.update(total=len(unique), returned=len(chosen), accepted=len(chosen), omitted=valid - len(chosen))
    return chosen, counts


def _key(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _project_policy_observation(macro):
    """A saved ECOS monthly observation, never a decision or issuer exposure.

    Legacy snapshots retain only source/stat_code. Identify those through the
    existing collector contract, explicitly disclosing the missing metadata.
    Never mutate the snapshot or treat the FRED copy as an independent source.
    """
    block = macro.get("macro") if isinstance(macro, dict) else None
    ecos = block.get("ecos") if isinstance(block, dict) else None
    counts = {"input": 0, "accepted": 0, "rejected": 0, "omitted": 0, "shape_errors": 0,
              "missing": not isinstance(ecos, dict) or "korea_policy_rate" not in ecos,
              "collector_contract_identity": 0}
    if counts["missing"]:
        return [], counts
    counts["input"] = 1
    row = ecos["korea_policy_rate"]
    observed = _stamp(macro.get("collected_at"))
    if (not isinstance(row, dict) or not observed or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})", observed)):
        counts["rejected"] = 1
        return [], counts
    clock = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    raw_period, value = row.get("date"), _finite_number(row.get("value"))
    if (clock > datetime.now(timezone.utc) or row.get("source") != "ecos"
            or row.get("stat_code") != ECOS_POLICY_SERIES["stat_code"]
            or not isinstance(raw_period, str) or not re.fullmatch(r"[0-9]{4}(0[1-9]|1[0-2])", raw_period)
            or raw_period[:4] == "0000"
            or raw_period > clock.astimezone(timezone(timedelta(hours=9))).strftime("%Y%m")
            or value is None or abs(value) > 1e20 or row.get("unit") != "연%"
            or any(key in row and row[key] != expected for key, expected in ECOS_POLICY_SERIES.items())):
        counts["rejected"] = 1
        return [], counts
    retained = all(key in row for key in ECOS_POLICY_SERIES)
    period = raw_period[:4] + "-" + raw_period[4:]
    counts.update(accepted=1, collector_contract_identity=int(not retained))
    return [{"id": "market:policy-rate:korea-base", "kind": "policy-rate", "title": "한국은행 기준금리",
        "summary": period + " · 월 단위 관측값", "source": "한국은행 ECOS · 공개 스냅샷",
        "url": ECOS_POLICY_SERIES["source_url"], "as_of": None, "observed_at": observed,
        "value": value, "change_pct": None, "unit": "연%", "company_ids": [], "basis": "market-context",
        "observation": {"period": period, **{key: val for key, val in ECOS_POLICY_SERIES.items() if key != "source_url"},
                        "identity_basis": "preserved-source" if retained else "collector-contract"},
        "verified_common_event": False,
        "reason": "ECOS 월 단위 관측값이에요. 정책 결정일·기간 중 변동·종목별 영향은 확인하지 않았어요. "
                  + ("출처 주소는 ECOS 포털이며 개별 관측값의 원문 조회 주소는 아니에요." if retained else
                     "보존 자료의 일부 시계열 식별자가 없어 기존 수집기 설정을 참고했어요. 월별 API 원문은 재조회하지 않았어요.")}], counts


def index_public_news_names(company_catalog):
    """Prepare public names only; never retain a selection or response."""
    aliases = {}
    for row in company_catalog if isinstance(company_catalog, list) else ():
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            name = safe_public_text(row.get("name"), 160)
            if name:
                aliases.setdefault(_key(name), set()).add(row["id"])
    return {"aliases": {name: frozenset(ids) for name, ids in aliases.items()
                        if len(name) >= 3 and len(ids) == 1},
            "catalog_names": frozenset(aliases)}


def _mention(title, name, catalog_names=()):
    korean_postpositions = ("에서", "에게", "는", "은", "가", "이", "의", "와", "과", "을", "를", "에")
    start = 0
    while True:
        index = title.find(name, start)
        if index < 0:
            return False
        end = index + len(name)
        if index == 0 or not title[index - 1].isalnum():
            if end == len(title) or not title[end].isalnum():
                return True
            for postposition in korean_postpositions:
                particle_end = end + len(postposition)
                if title.startswith(postposition, end) and (
                        particle_end == len(title) or not title[particle_end].isalnum()):
                    if name + postposition in catalog_names:
                        continue
                    return True
        start = index + 1


def _report_key(row):
    url, title, source, stamp, _ = row
    # Only Google News' explicit publisher suffix is presentation metadata.
    # Never strip numbers, correction labels, punctuation or headline words.
    if urlsplit(url).hostname == "news.google.com" and title.endswith(" - " + source):
        title = title[:-(len(source) + 3)]
    day = datetime.fromisoformat(stamp).astimezone(timezone.utc).date().isoformat()
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).lower().split())
    return "\n".join(("same-publisher-headline-day", normalize(source), normalize(title), day))


def project_market_context(documents, selected_companies, company_catalog, filing_context=None, filing_excerpts=None,
                           *, news_name_index=None):
    """Return bounded indicators, reported roles, release calendars and headlines."""
    documents = documents if isinstance(documents, dict) else {}
    source_names = ("macro_snapshot.json", "commodity_exposure.json", "portfolio.json")
    by_source = {name: {"input": 0, "accepted": 0, "rejected": 0, "omitted": 0, "shape_errors": 0,
                        "missing": name not in documents} for name in source_names}
    missing = sum(row["missing"] for row in by_source.values())
    coverage = {"status": "not-supplied" if missing == len(source_names) else "partial" if missing else "complete",
                "input": 0, "accepted": 0, "rejected": 0, "missing_sources": missing, "by_source": by_source}
    selected = {row.get("id") for row in selected_companies if isinstance(row, dict)}
    news_names = index_public_news_names(company_catalog) if news_name_index is None else news_name_index
    catalog_names = news_names["catalog_names"]
    aliases = {name: next(iter(ids)) for name, ids in news_names["aliases"].items()
               if next(iter(ids)) in selected}
    items = []
    exposure = documents.get("commodity_exposure.json")
    table = exposure.get("commodities") if isinstance(exposure, dict) else None
    exposure_tickers = {}
    if isinstance(table, dict):
        for code, (kind, _) in MARKET_SPECS.items():
            if kind != "commodity" or code not in table:
                continue
            entry = table[code]
            stocks = entry.get("stocks") if isinstance(entry, dict) else None
            counter = by_source["commodity_exposure.json"]
            if not isinstance(stocks, list):
                counter["shape_errors"] += 1
                continue
            counter["input"] += len(stocks)
            tickers = set()
            for stock in stocks:
                ticker = stock.get("ticker") if isinstance(stock, dict) else None
                if not isinstance(ticker, str) or not re.fullmatch(r"[0-9]{6}", ticker):
                    counter["rejected"] += 1
                    continue
                tickers.add(ticker);counter["accepted"] += 1
            exposure_tickers[code] = tickers
    elif "commodity_exposure.json" in documents:
        by_source["commodity_exposure.json"]["shape_errors"] += 1
    macro = documents.get("macro_snapshot.json")
    if isinstance(macro, dict) and isinstance(macro.get("macro"), dict):
        for code, (kind, title) in MARKET_SPECS.items():
            row = macro["macro"].get(code)
            if not isinstance(row, dict):
                continue
            by_source["macro_snapshot.json"]["input"] += 1
            value, change = _finite_number(row.get("value")), _finite_number(row.get("change_pct"))
            if row.get("status") != "ok" or value is None or change is None:
                by_source["macro_snapshot.json"]["rejected"] += 1
                continue
            as_of = row.get("data_date")
            if not isinstance(as_of, str) or not _DATE.fullmatch(as_of):
                as_of = None
            elif not _valid_date(as_of):
                as_of = None
            linked, basis = [], "market-context"
            if kind == "commodity":
                tickers = exposure_tickers.get(code, set())
                linked = sorted(identifier for identifier in selected if isinstance(identifier, str)
                                and identifier.startswith("KR:") and identifier[3:] in tickers)
                if linked:
                    basis = "industry-membership"
            industry_ids = linked[:]
            refs = [dict(ref) for ref in (filing_context or {}).get("by_indicator", {}).get(code, [])
                    if ref["company_id"] in selected]
            if refs:
                linked = sorted(set(linked) | {ref["company_id"] for ref in refs})
                basis = "filing-context"
            fx_unit = {"usd_krw": "KRW per USD", "usd_jpy": "JPY per USD", "eur_usd": "USD per EUR"}.get(code)
            raw_source = safe_public_text(row.get("source"), 80)
            items.append({"id": f"market:{kind}:{code}", "kind": kind, "title": title,
                "summary": "환율 시장 지표" if kind == "fx" else "원자재 시장 지표",
                "source": f"{raw_source} · 공개 스냅샷" if raw_source else "공개 시장 스냅샷",
                "url": MACRO_URL, "as_of": as_of,
                "observed_at": _stamp(row.get("as_of")), "value": value, "change_pct": change,
                "unit": fx_unit if kind == "fx" else None, "company_ids": linked, "basis": basis,
                "reason": ("사업보고서의 관련 표현과 시장 참고 지표를 연결했어요. 노출 규모·현재 영향·등락 방향은 미확인이에요." if refs else
                           "산업 분류 후보이며 매출 노출이나 영향이 확인된 것은 아닙니다." if linked else "공개 지표이며 기업별 관계를 뜻하지 않습니다."),
                **({"filing_refs": refs, "industry_company_ids": industry_ids} if refs else {})})
            by_source["macro_snapshot.json"]["accepted"] += 1
    elif "macro_snapshot.json" in documents:
        by_source["macro_snapshot.json"]["shape_errors"] += 1

    calendar, calendar_counts = _project_release_calendar(macro)
    items.extend(calendar)
    coverage["release_calendar"] = calendar_counts
    for key in ("input", "accepted", "rejected", "omitted", "shape_errors"):
        by_source["macro_snapshot.json"][key] += calendar_counts[key]

    policy, policy_counts = _project_policy_observation(macro)
    items.extend(policy)
    coverage["policy_observation"] = policy_counts
    for key in ("input", "accepted", "rejected", "omitted", "shape_errors"):
        by_source["macro_snapshot.json"][key] += policy_counts[key]

    # A shared disclosed risk is not a numeric rate, benchmark match or common
    # event. Each member retains its own dated filing and full qualifying quote.
    rate_refs = {}
    for ref in sorted((filing_excerpts or {}).get("rates", []), key=lambda row: (row["as_of"], row["url"]), reverse=True):
        if ref["company_id"] in selected:
            rate_refs.setdefault(ref["company_id"], ref)
    if rate_refs:
        items.append({"id": "market:interest-risk:floating-borrowing", "kind": "interest-risk",
            "title": "변동금리 차입 위험", "summary": "보고서에 명시된 금리위험 공시 묶음",
            "source": "DART · 보고기간별 공시", "url": "https://dart.fss.or.kr/",
            "as_of": None, "observed_at": None, "value": None, "change_pct": None, "unit": None,
            "company_ids": sorted(rate_refs), "basis": "filing-context", "industry_company_ids": [],
            "filing_refs": [rate_refs[key] for key in sorted(rate_refs)],
            "evidence_revision": filing_excerpts["rates_revision"],
            "reason": "각 회사가 보고 당시 변동금리 차입 위험을 공시했어요. 서로 다른 보고기간의 자료이며 같은 사건이나 현재 차입 규모·순영향을 뜻하지 않아요. 특정 기준금리와의 연동은 미확인이에요."})
    if filing_excerpts is not None and filing_excerpts.get("coverage", {}).get("input"):
        coverage["cached_filing_excerpts"] = dict(filing_excerpts["coverage"])

    # Reuse the same per-filing proof path without inventing a tariff, current
    # demand shock, stock-price direction or a confirmed common economic event.
    power = (filing_context or {}).get("power", {})
    returned_power_refs = 0
    for role, (_, title) in _POWER_ROLES.items():
        catalog_refs = sorted(power.get("by_role", {}).get(role, []), key=lambda ref: ref["company_id"])
        refs = [deepcopy(ref) for ref in catalog_refs if ref["company_id"] in selected]
        if not refs:
            continue
        revision = hashlib.sha256(json.dumps(catalog_refs, sort_keys=True,
            ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
        items.append({"id": "market:power-context:" + role, "kind": "power-context",
            "title": title, "summary": "보고서에 명시된 전력 관련 사업 경로",
            "source": "DART · 보고기간별 공시", "url": "https://dart.fss.or.kr/",
            "as_of": None, "observed_at": None, "value": None, "change_pct": None, "unit": None,
            "company_ids": sorted({ref["company_id"] for ref in refs}), "basis": "filing-context",
            "industry_company_ids": [], "filing_refs": refs, "evidence_revision": revision,
            "reason": "각 회사가 보고 당시 명시한 전력 관련 사업 경로를 묶었어요. 서로 다른 보고기간의 자료이며 같은 사건·기업 간 거래 관계를 뜻하지 않아요. 전력요금·노출 규모·현재 상태·주가 영향은 미확인이에요."})
        returned_power_refs += len(refs)
    if power:
        coverage["power_context"] = {**power.get("coverage", {}), "returned_references": returned_power_refs}

    # This is a reported operating fact only. It does not establish a current
    # concession, policy benefit, company relationship or common event.
    infrastructure = (filing_context or {}).get("infrastructure", {})
    returned_infrastructure_refs = 0
    for role, title in _INFRASTRUCTURE_ROLES.items():
        catalog_refs = sorted(infrastructure.get("by_role", {}).get(role, []),
                              key=lambda ref: ref["company_id"])
        refs = [deepcopy(ref) for ref in catalog_refs if ref["company_id"] in selected]
        if not refs:
            continue
        revision = hashlib.sha256(json.dumps(catalog_refs, sort_keys=True,
            ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
        items.append({"id": "market:infrastructure-context:" + role,
            "kind": "infrastructure-context", "title": title,
            "summary": "보고서에 명시된 항만·터미널 운영 사실",
            "source": "DART · 보고기간별 공시", "url": "https://dart.fss.or.kr/",
            "as_of": None, "observed_at": None, "value": None, "change_pct": None, "unit": None,
            "company_ids": sorted({ref["company_id"] for ref in refs}), "basis": "filing-context",
            "industry_company_ids": [], "filing_refs": refs, "evidence_revision": revision,
            "reason": "각 회사가 보고 당시 명시한 항만·터미널 운영 사실을 묶었어요. 같은 사건·기업 간 거래 관계나 현재 정책 수혜를 뜻하지 않아요. 현재 운영권·사업 규모·주가 영향은 미확인이에요."})
        returned_infrastructure_refs += len(refs)
    if infrastructure:
        coverage["infrastructure_context"] = {**infrastructure.get("coverage", {}),
            "returned_references": returned_infrastructure_refs}

    portfolio = documents.get("portfolio.json")
    candidates = []
    if isinstance(portfolio, dict):
        for feed in NEWS_FEEDS:
            rows = portfolio.get(feed, [])
            if not isinstance(rows, list):
                by_source["portfolio.json"]["shape_errors"] += 1
                continue
            by_source["portfolio.json"]["input"] += len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    by_source["portfolio.json"]["rejected"] += 1
                    continue
                title = safe_public_text(row.get("title") or row.get("title_ko"), 240)
                source = safe_public_text(row.get("source"), 100)
                url, stamp = _url(row.get("link")), _news_date(row.get("time"))
                if not title or not source or not url or not stamp:
                    by_source["portfolio.json"]["rejected"] += 1
                    continue
                title_key = _key(title)
                linked = sorted({identifier for name, identifier in aliases.items()
                                 if _mention(title_key, name, catalog_names)})
                candidates.append((url, title, source, stamp, linked))
    elif "portfolio.json" in documents:
        by_source["portfolio.json"]["shape_errors"] += 1
    unique = {}
    for row in sorted(candidates, key=lambda row: datetime.fromisoformat(row[3]).timestamp(), reverse=True):
        unique.setdefault(row[0], row)
    grouped = {}
    for row in unique.values():
        grouped.setdefault(_report_key(row), []).append(row)
    rows = sorted(grouped.items(), key=lambda group: (
        max(datetime.fromisoformat(row[3]).timestamp() for row in group[1]), group[0]), reverse=True)
    matched = lambda group: any(row[4] for row in group[1])
    selected_groups = [group for group in rows if matched(group)][:20]
    # Keep the same 25-card bound, but do not leave 20 slots empty when the
    # selected stocks have no exact full-name headline mentions.
    chosen = selected_groups + [group for group in rows if not matched(group)][:25 - len(selected_groups)]
    for key, members in chosen:
        members = sorted(members, key=lambda row: (-datetime.fromisoformat(row[3]).timestamp(), row[0]))[:8]
        url, title, source, stamp, _ = members[0]
        linked = sorted({identifier for member in members for identifier in member[4]})
        reports = [{"url": row[0], "title": row[1], "source": row[2], "as_of": row[3]}
                   for row in sorted(members, key=lambda row: row[0])]
        items.append({"id": "market:news:" + hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "kind": "news", "title": title, "summary": source, "source": source, "url": url,
            "as_of": stamp, "observed_at": None, "value": None, "change_pct": None, "unit": None,
            "company_ids": linked, "basis": "name-mention" if linked else "market-context",
            "reports": reports, "grouping": "same-publisher-headline-day", "verified_common_event": False,
            "reason": "고유한 기업명 전체가 제목에 있으나 사업 관계의 증거는 아닙니다." if linked else "일반 시장 기사이며 기업 관계를 추론하지 않습니다."})
        by_source["portfolio.json"]["accepted"] += len(reports)
    by_source["portfolio.json"]["omitted"] = len(candidates) - by_source["portfolio.json"]["accepted"]
    coverage["news_groups"] = {"total": len(rows), "returned": len(chosen),
                               "omitted": len(rows) - len(chosen),
                               "grouped": sum(len(members) > 1 for _, members in rows)}
    coverage["input"] = sum(row["input"] for row in by_source.values())
    coverage["accepted"] = sum(row["accepted"] for row in by_source.values())
    coverage["rejected"] = sum(row["rejected"] for row in by_source.values())
    coverage["omitted"] = sum(row["omitted"] for row in by_source.values())
    coverage["shape_errors"] = sum(row["shape_errors"] for row in by_source.values())
    coverage["returned_items"] = len(items)
    if filing_context is not None:
        coverage["filing_context"] = {**filing_context["coverage"],
            "returned_references": sum(len(item.get("filing_refs", [])) for item in items)}
    if coverage["rejected"] or coverage["shape_errors"] or coverage["omitted"]:
        coverage["status"] = "partial"
    return {"schema": SCHEMA, "items": items, "coverage": coverage}


def _valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
