"""
Visitor Geolocation — Vercel Edge Geo headers 기반.

GET /api/visitor_ping
  → Vercel infra (MaxMind GeoIP2) 가 주입한 x-vercel-ip-* 헤더를 읽어
    { country_code, place_label } 반환. 클라이언트는 이 값을 Supabase
    live_visitors 테이블에 upsert 하는 데 사용.

외부 의존 없음 (ipwho.is 대체). CORS: 모든 origin.
한국어 매핑 dict 는 LiveVisitors.tsx 의 GEO_EN_TO_KO 를 이관.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import unquote

try:
    import requests  # Vercel Python runtime 기본 포함
except ImportError:
    requests = None  # type: ignore


# ── ISO 3166-2:KR 행정구역 코드 → 한국어 ──
# Vercel x-vercel-ip-country-region 은 ISO 번호 부분만 보냄 (예: "41").
_KR_REGION_ISO = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천",
    "29": "광주", "30": "대전", "31": "울산", "41": "경기",
    "42": "강원", "43": "충북", "44": "충남", "45": "전북",
    "46": "전남", "47": "경북", "48": "경남", "49": "제주",
    "50": "세종",
}

# ── 영문 지명 → 한국어 (도시/시/군 · "-si"/"-gun" 접미사 포함) ──
_KR_CITY_EN_TO_KO = {
    "seoul": "서울", "busan": "부산", "incheon": "인천", "daegu": "대구",
    "daejeon": "대전", "gwangju": "광주", "ulsan": "울산", "sejong": "세종",
    "gimpo": "김포", "suwon": "수원", "yongin": "용인", "seongnam": "성남",
    "bucheon": "부천", "ansan": "안산", "anyang": "안양", "uijeongbu": "의정부",
    "pyeongtaek": "평택", "goyang": "고양", "gwacheon": "과천", "hanam": "하남",
    "namyangju": "남양주", "hwaseong": "화성", "siheung": "시흥", "gunpo": "군포",
    "icheon": "이천", "anseong": "안성", "guri": "구리", "osan": "오산",
    "paju": "파주", "yangju": "양주", "yeoju": "여주", "dongducheon": "동두천",
    "gapyeong": "가평", "yangpyeong": "양평", "yeoncheon": "연천",
    "cheonan": "천안", "cheongju": "청주", "jeonju": "전주", "chuncheon": "춘천",
    "wonju": "원주", "gangneung": "강릉", "sokcho": "속초", "pohang": "포항",
    "gyeongju": "경주", "changwon": "창원", "seogwipo": "서귀포",
    "jeju": "제주시",
}


def _norm_city_key(raw: str) -> str:
    """영문 지명 정규화: 소문자, 공백→하이픈, 특수문자 제거, 접미사 제거."""
    t = raw.strip().lower().replace(" ", "-")
    for ch in (".", "'", "’"):
        t = t.replace(ch, "")
    # 접미사 제거 (gimpo-si → gimpo, yangpyeong-gun → yangpyeong)
    for suffix in ("-si", "-gun", "-do"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    return t


def _map_kr_city(raw: str) -> str:
    """KR 도시명 한국어 매핑. 실패 시 원문 그대로."""
    if not raw:
        return ""
    key = _norm_city_key(raw)
    return _KR_CITY_EN_TO_KO.get(key, raw)


def _build_place_label(headers: dict) -> dict:
    """Vercel geo headers → { country_code, place_label }.

    KR: '경기 김포시' 형태 (region 한글 + city 한글)
    해외: 'Tokyo, JP' 형태 (city + country code)
    geo 헤더 없음: 둘 다 None
    """
    # http.server headers 는 case-insensitive 지만 명시적으로 소문자 lookup
    def _h(key: str) -> str:
        for k in (key, key.upper(), key.title()):
            if k in headers and headers[k]:
                return headers[k]
        return ""

    country = _h("x-vercel-ip-country").upper().strip()
    region_iso = _h("x-vercel-ip-country-region").strip()
    city_raw = unquote(_h("x-vercel-ip-city")).strip()

    if not country:
        return {"country_code": None, "place_label": None}

    if country == "KR":
        region_ko = _KR_REGION_ISO.get(region_iso, "")
        city_ko = _map_kr_city(city_raw)
        parts = [p for p in (region_ko, city_ko) if p]
        label = " ".join(parts) if parts else "한국"
        return {"country_code": "KR", "place_label": label[:100]}

    # 해외 — city 우선, 없으면 country code
    if city_raw and country:
        label = f"{city_raw}, {country}"
    elif city_raw:
        label = city_raw
    else:
        label = country
    return {"country_code": country, "place_label": label[:100]}


def _extract_client_ip(headers: dict) -> str:
    xff = headers.get("x-forwarded-for", "") or headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return headers.get("x-real-ip", "") or headers.get("X-Real-IP", "") or ""


def _ipapi_fallback(client_ip: str) -> dict:
    """Vercel geo 헤더가 비었을 때 ipapi.co 직접 조회 (무료 1k/day, HTTPS)."""
    if requests is None or not client_ip or client_ip.startswith(("127.", "10.", "192.168.")):
        return {"country_code": None, "place_label": None}
    try:
        r = requests.get(f"https://ipapi.co/{client_ip}/json/", timeout=3)
        if not r.ok:
            return {"country_code": None, "place_label": None}
        j = r.json()
        cc = (j.get("country_code") or "").upper().strip()
        region = (j.get("region") or "").strip()
        city = (j.get("city") or "").strip()
        if not cc:
            return {"country_code": None, "place_label": None}
        if cc == "KR":
            # region 이 이름("Gyeonggi-do") 으로 올 수 있음 — 한글 dict 재사용
            region_key = region.lower().replace(" ", "-").rstrip(".'")
            region_ko = _KR_CITY_EN_TO_KO.get(region_key, region)
            # 추가로 도 매핑
            region_ko_map = {
                "gyeonggi": "경기", "gyeonggi-do": "경기",
                "gangwon": "강원", "gangwon-do": "강원", "gangwon-state": "강원",
                "chungcheongbuk-do": "충북", "chungcheongnam-do": "충남",
                "jeollabuk-do": "전북", "jeollanam-do": "전남",
                "gyeongsangbuk-do": "경북", "gyeongsangnam-do": "경남",
                "jeju": "제주", "jeju-do": "제주",
            }
            if region_key in region_ko_map:
                region_ko = region_ko_map[region_key]
            city_ko = _map_kr_city(city)
            parts = [p for p in (region_ko, city_ko) if p]
            return {"country_code": "KR", "place_label": (" ".join(parts) if parts else "한국")[:100]}
        # 해외
        label = f"{city}, {cc}" if city else cc
        return {"country_code": cc, "place_label": label[:100]}
    except Exception:
        return {"country_code": None, "place_label": None}


class handler(BaseHTTPRequestHandler):
    def _respond_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            headers = {k.lower(): v for k, v in self.headers.items()}
            # 1차: Vercel Edge Geo 헤더
            result = _build_place_label(headers)
            if result.get("country_code") and result.get("place_label"):
                result["source"] = "vercel_geo"
                self._respond_json(result)
                return
            # 2차: ipapi.co 서버측 fallback (Vercel geo 헤더 비었을 때)
            client_ip = _extract_client_ip(headers)
            fb = _ipapi_fallback(client_ip)
            if fb.get("country_code"):
                fb["source"] = "ipapi_fallback"
                self._respond_json(fb)
                return
            # 둘 다 실패
            self._respond_json({"country_code": None, "place_label": None, "source": "none"})
        except Exception as e:
            self._respond_json({"country_code": None, "place_label": None, "error": str(e)[:100]}, 200)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
