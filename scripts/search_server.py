#! /usr/bin/python3
"""search_server.py — wblog 本地全功能预览服务（开发用）

静态服务 out/dist（SPA 友好），并提供 /api/search 查 SQLite（out/index.db）。
与生产 OpenResty 的 /api/search 保持同一契约/逻辑：
  长词(>=3 字符) → FTS5 trigram MATCH；短词(1-2) → LIKE 兜底（trigram 最小 3 字符）。
  返回 {"results":[{path,title,snippet}]}，snippet 为含查询词的原文片段(纯文本，前端负责 escape+高亮)。

用法: python3 search_server.py [--root out/dist] [--db out/index.db] [--port 9999]
"""
import argparse
import functools
import http.server
import json
import os
import re
import sqlite3
import urllib.parse

FTS_SPECIAL = re.compile(r'["*():^]')


class WblogHandler(http.server.SimpleHTTPRequestHandler):
    db_path = ''

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/search':
            self.handle_search(urllib.parse.parse_qs(parsed.query))
            return
        # SPA 路径补 .html：/articles/x/index → /articles/x/index.html
        full = os.path.join(self.directory, parsed.path.lstrip('/'))
        if os.path.isfile(full + '.html'):
            self.path = parsed.path + '.html'
        return super().do_GET()

    def handle_search(self, params):
        q = (params.get('q') or [''])[0].strip()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if not q:
            self.wfile.write(json.dumps({'results': []}).encode())
            return
        try:
            results = self.search_db(q)
            self.wfile.write(json.dumps({'results': results}, ensure_ascii=False).encode())
        except Exception as e:  # noqa: BLE001
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def search_db(self, q, limit=20):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if len(q) >= 3 and not FTS_SPECIAL.search(q):
                rows = conn.execute(
                    "SELECT url, title, body FROM pages_fts WHERE pages_fts MATCH ? "
                    "ORDER BY rank LIMIT ?", (q, limit)).fetchall()
            else:
                like = f'%{q}%'
                rows = conn.execute(
                    "SELECT url, title, body FROM pages_fts "
                    "WHERE body LIKE ? OR title LIKE ? LIMIT ?",
                    (like, like, limit)).fetchall()
            out = []
            for r in rows:
                # SPA path（无 /articles 前缀）：/articles/std/index.html → /std/index
                path = r['url'].replace('/articles/', '/').removesuffix('.html')
                out.append({
                    'path': path,
                    'title': r['title'],
                    'snippet': self.around(r['body'] or '', q),
                })
            return out
        finally:
            conn.close()

    @staticmethod
    def around(body, q, radius=45):
        """返回含 q 的原文片段（纯文本，不做 HTML escape——前端负责）。"""
        idx = body.find(q)
        if idx < 0:
            return body[: radius * 2]
        s = body[max(0, idx - radius): idx + len(q) + radius]
        if idx > radius:
            s = '…' + s
        if idx + len(q) + radius < len(body):
            s = s + '…'
        return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='out/dist')
    ap.add_argument('--db', default='out/index.db')
    ap.add_argument('--port', type=int, default=9999)
    args = ap.parse_args()
    root, db = os.path.abspath(args.root), os.path.abspath(args.db)
    handler = functools.partial(WblogHandler, directory=root)
    WblogHandler.db_path = db
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', args.port), handler)
    print(f'wblog preview: http://localhost:{args.port}/template/template.html (root={root}, db={db})')
    srv.serve_forever()


if __name__ == '__main__':
    main()
