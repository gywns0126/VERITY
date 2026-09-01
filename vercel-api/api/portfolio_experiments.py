"""Portfolio experiment drafts and public learning feed.

GET  /api/portfolio_experiments?limit=30  public experiments, privacy-sanitized
GET  /api/portfolio_experiments?mine=1    authenticated user's experiments
POST /api/portfolio_experiments           create a draft or published experiment
DELETE /api/portfolio_experiments {id}     delete own experiment

No performance result is accepted from the client. Verified calculation output will
be added only when the historical price, dividend, tax, and fee engine is connected.
"""
from http.server import BaseHTTPRequestHandler
from collections import defaultdict
import json
import logging
import time
import traceback
from urllib.parse import parse_qs, urlparse

try:
    import api.supabase_client as sb
except ModuleNotFoundError:  # direct module tests
    import supabase_client as sb

_logger = logging.getLogger(__name__)
_rate_limit = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 60
_PRIVACY = {"private", "summary", "masked", "full"}
_FREQUENCY = {"monthly", "quarterly", "once"}
_REBALANCE = {"yearly", "quarterly", "none"}


def _cors(h):
    try:
        from api.cors_helper import resolve_origin
        origin = resolve_origin(h.headers.get("Origin") or "")
    except Exception:
        origin = ""
    if origin:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def _json(h, data, status=200):
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    _cors(h)
    h.end_headers()
    h.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def _body(h):
    try:
        return json.loads(h.rfile.read(int(h.headers.get("Content-Length", 0) or 0)).decode() or "{}")
    except Exception:
        return {}


def _jwt(h):
    auth = (h.headers.get("Authorization") or "").strip()
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


def _limit_ok(h):
    ip = (h.headers.get("x-forwarded-for") or "").split(",")[0].strip() or "unknown"
    now = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < _RATE_WINDOW]
    if len(_rate_limit[ip]) >= _RATE_MAX:
        return False
    _rate_limit[ip].append(now)
    return True


def _clean_assets(value):
    if not isinstance(value, list):
        return None
    out = []
    for raw in value[:30]:
        if not isinstance(raw, dict):
            continue
        ticker = str(raw.get("ticker") or "").strip()[:20]
        name = str(raw.get("name_ko") or raw.get("name") or ticker).strip()[:100]
        market = str(raw.get("market") or "").strip()[:12]
        asset_type = str(raw.get("type") or "").strip()[:24]
        instrument_type = str(raw.get("instrument_type") or "").strip()[:32]
        underlying_symbol = str(raw.get("underlying_symbol") or "").strip()[:20]
        try:
            weight = round(float(raw.get("weight") or 0), 2)
        except (TypeError, ValueError):
            weight = 0
        if ticker and 0 <= weight <= 100:
            item = {"ticker": ticker, "name": name, "market": market, "weight": weight}
            if asset_type:
                item["type"] = asset_type
            if instrument_type:
                item["instrument_type"] = instrument_type
            if underlying_symbol:
                item["underlying_symbol"] = underlying_symbol
            out.append(item)
    if not out or abs(sum(x["weight"] for x in out) - 100) > 0.02:
        return None
    return out


def _public_item(row, profiles):
    privacy = str(row.get("privacy") or "summary")
    assets = row.get("assets") if isinstance(row.get("assets"), list) else []
    if privacy == "summary":
        visible_assets = []
    elif privacy == "masked":
        visible_assets = [{"market": x.get("market") or "기타", "weight": x.get("weight")} for x in assets]
    else:
        visible_assets = assets
    profile = profiles.get(row.get("user_id"), {})
    return {
        "id": row.get("id"),
        "kind": "portfolio_experiment",
        "nickname": profile.get("nickname") or "익명",
        "avatar": profile.get("avatar") or "",
        "title": row.get("title") or "포트폴리오 실험",
        "assets": visible_assets,
        "asset_count": len(assets),
        "start_date": row.get("start_date"),
        "contribution": row.get("contribution"),
        "frequency": row.get("frequency"),
        "rebalance": row.get("rebalance"),
        "dividend_reinvest": bool(row.get("dividend_reinvest")),
        "privacy": privacy,
        "created_at": row.get("created_at"),
        "result_status": "engine_not_connected",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        if not _limit_ok(self):
            return _json(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json(self, {"items": []})
        qs = parse_qs(urlparse(self.path).query)
        token = _jwt(self)
        user_id = sb.verify_jwt(token) if token else None
        mine = (qs.get("mine", [""])[0] or "") in ("1", "true")
        if mine and not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        try:
            limit = max(1, min(50, int(qs.get("limit", ["30"])[0] or 30)))
        except Exception:
            limit = 30
        filters = {
            "select": "id,user_id,title,assets,start_date,contribution,frequency,rebalance,dividend_reinvest,privacy,status,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        if mine:
            filters["user_id"] = f"eq.{user_id}"
        else:
            filters.update({"status": "eq.published", "hidden": "eq.false", "privacy": "neq.private"})
        try:
            rows = sb.select("portfolio_experiments", filters, user_jwt=token or None)
            if mine:
                return _json(self, {"items": rows or []})
            uids = ",".join(sorted({str(x.get("user_id")) for x in rows or [] if x.get("user_id")}))
            profiles = {}
            if uids:
                for profile in sb.select("public_profiles", {"id": f"in.({uids})", "select": "id,nickname,avatar"}):
                    profiles[profile["id"]] = profile
            return _json(self, {"items": [_public_item(row, profiles) for row in rows or []]})
        except Exception as exc:
            _logger.error("portfolio experiments GET: %s\n%s", exc, traceback.format_exc())
            return _json(self, {"items": []})

    def do_POST(self):
        if not _limit_ok(self):
            return _json(self, {"error": "요청이 너무 많습니다"}, 429)
        token = _jwt(self)
        user_id = sb.verify_jwt(token) if token else None
        if not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        data = _body(self)
        assets = _clean_assets(data.get("assets"))
        if not assets:
            return _json(self, {"error": "자산 비중 합계가 100%인지 확인해주세요"}, 400)
        privacy = str(data.get("privacy") or "private")
        frequency = str(data.get("frequency") or "monthly")
        rebalance = str(data.get("rebalance") or "yearly")
        if privacy not in _PRIVACY or frequency not in _FREQUENCY or rebalance not in _REBALANCE:
            return _json(self, {"error": "설정값을 확인해주세요"}, 400)
        try:
            contribution = float(data.get("amount") or 0)
        except (TypeError, ValueError):
            contribution = 0
        if contribution <= 0:
            return _json(self, {"error": "투자 금액을 확인해주세요"}, 400)
        published = privacy != "private" and bool(data.get("publish"))
        payload = {
            "user_id": user_id,
            "title": str(data.get("title") or "나의 포트폴리오 실험").strip()[:80],
            "assets": assets,
            "start_date": str(data.get("start") or "")[:10],
            "contribution": contribution,
            "frequency": frequency,
            "rebalance": rebalance,
            "dividend_reinvest": bool(data.get("dividend")),
            "privacy": privacy,
            "status": "published" if published else "draft",
        }
        try:
            row = sb.insert("portfolio_experiments", payload, user_jwt=token)
            return _json(self, row, 201)
        except Exception as exc:
            _logger.error("portfolio experiments POST: %s\n%s", exc, traceback.format_exc())
            return _json(self, {"error": "실험을 저장하지 못했어요"}, 500)

    def do_DELETE(self):
        token = _jwt(self)
        user_id = sb.verify_jwt(token) if token else None
        if not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        experiment_id = str(_body(self).get("id") or "").strip()
        if not experiment_id:
            return _json(self, {"error": "id 필요"}, 400)
        try:
            sb.delete("portfolio_experiments", {"id": experiment_id, "user_id": user_id}, user_jwt=token)
            return _json(self, {"ok": True})
        except Exception:
            return _json(self, {"error": "삭제하지 못했어요"}, 500)
