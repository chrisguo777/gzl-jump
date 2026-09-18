"""Allowlisted loopback preview: never serve exports, source or private data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/images/gzl.png': ('images/gzl.png', 'image/png'),
          '/vendor/three.min.js': ('vendor/three.min.js', 'application/javascript')}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            self.send_error(403)
            return
        asset = ASSETS.get(urlsplit(self.path).path)
        if not asset:
            self.send_error(404)
            return
        path = ROOT / asset[0]
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            self.send_error(404)
            return
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', asset[1])
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    print('安全游戏预览：http://127.0.0.1:8888/')
    ThreadingHTTPServer(('127.0.0.1', 8888), Handler).serve_forever()
