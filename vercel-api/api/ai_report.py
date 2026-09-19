"""Legacy AI PDF URL: the same evidence report, without model calls.

PM 2026-09-17: retain old bookmarks; never restore paid narrative generation.
The explicit HTTP subclass is required by Vercel's Python entrypoint detector.
"""
from http.server import BaseHTTPRequestHandler
if __package__:
    from .fact_report import handler as ReportHandler
else:
    from fact_report import handler as ReportHandler


class handler(BaseHTTPRequestHandler):
    _cors = ReportHandler._cors
    _err = ReportHandler._err

    def do_OPTIONS(self):
        return ReportHandler.do_OPTIONS(self)

    def do_GET(self):
        return ReportHandler.do_GET(self)
