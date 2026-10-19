"""Compatibility redirect only; no QuantLab UI, database, scheduler or API client."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET = 'https://quantbet-research-production.up.railway.app/research/analytics/corners'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/livez':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok\n')
            return
        self.send_response(308)
        self.send_header('Location', TARGET)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()


def main():
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()


if __name__ == '__main__':
    main()
