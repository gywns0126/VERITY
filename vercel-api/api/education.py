"""Public, read-only education snapshot. No auth, user data, or write methods."""
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import parse_qs, urlparse

from content_site import load_site
from content_public import PublicSourceError


class handler(BaseHTTPRequestHandler):
    def _reply(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=60, s-maxage=60, must-revalidate" if status == 200 else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Allow", "GET, OPTIONS")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True, max_num_fields=4)
            if any(len(v) != 1 for v in query.values()):
                raise ValueError("Duplicate query")
            args = {key: value[0] for key, value in query.items()}
            args.setdefault("source", "lessons")
            if args["source"] not in ("lessons", "guides"):
                raise ValueError("Invalid source")
            for key in ("limit", "offset"):
                if key in args:
                    if not args[key].isascii() or not args[key].isdigit():
                        raise ValueError("Invalid range")
                    args[key] = int(args[key])
            return self._reply(load_site(args))
        except ValueError:
            return self._reply({"error": "invalid_arguments"}, 400)
        except PublicSourceError:
            return self._reply({"error": "education_unavailable"}, 503)

    def do_OPTIONS(self):
        return self._reply({"methods": ["GET", "OPTIONS"]})

    def _readonly(self):
        return self._reply({"error": "method_not_allowed"}, 405)

    do_POST = do_PUT = do_PATCH = do_DELETE = _readonly
