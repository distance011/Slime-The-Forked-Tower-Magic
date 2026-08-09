#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
史莱姆团 - 报名查询网页
在浏览器中查询玩家填了哪个车表、在哪个队、什么位置
用法: python web_query.py  然后浏览器打开 http://localhost:8000
"""

import json
import os
import sys
import time
import threading
import importlib.util
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "players_db.json")
PORT = 8000

spec = importlib.util.spec_from_file_location("ur", os.path.join(SCRIPT_DIR, "update_renshu.py"))
ur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ur)
spec2 = importlib.util.spec_from_file_location("qr", os.path.join(SCRIPT_DIR, "query_renshu.py"))
qr = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(qr)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>史莱姆团 - 报名查询</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: "Microsoft YaHei","PingFang SC",sans-serif; background:#f0f2f5; min-height:100vh; }
  .header { background:linear-gradient(135deg,#667eea,#764ba2); color:#fff; padding:24px 20px; text-align:center; }
  .header h1 { font-size:26px; margin-bottom:6px; }
  .header p { opacity:.9; font-size:14px; }
  .container { max-width:760px; margin:24px auto; padding:0 16px; }
  .search-box { background:#fff; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,.08); margin-bottom:20px; display:flex; gap:10px; }
  .search-box input { flex:1; padding:12px 16px; font-size:16px; border:2px solid #e0e0e0; border-radius:8px; outline:none; }
  .search-box input:focus { border-color:#667eea; }
  .search-box button { padding:12px 24px; font-size:16px; border:none; border-radius:8px; background:#667eea; color:#fff; cursor:pointer; }
  .search-box button:hover { background:#5568d8; }
  .status { text-align:center; color:#999; padding:12px; }
  .result { background:#fff; border-radius:12px; padding:16px 20px; box-shadow:0 2px 8px rgba(0,0,0,.08); margin-bottom:14px; border-left:4px solid #667eea; }
  .result .car { font-size:17px; font-weight:600; color:#333; margin-bottom:8px; }
  .result .meta { font-size:13px; color:#888; margin-bottom:8px; }
  .result .info { display:flex; flex-wrap:wrap; gap:16px; font-size:15px; }
  .result .info span b { color:#555; font-weight:600; }
  .badge { display:inline-block; background:#eef2ff; color:#667eea; border-radius:6px; padding:2px 10px; font-size:14px; font-weight:600; }
  .summary { background:#fff; border-radius:12px; padding:12px 20px; box-shadow:0 2px 8px rgba(0,0,0,.08); margin-bottom:16px; font-size:14px; color:#555; }
  .hint { text-align:center; color:#aaa; font-size:13px; margin-top:24px; padding-bottom:20px; }
  .tip { background:#fff8e6; border:1px solid #ffe7a0; border-radius:8px; padding:10px 14px; font-size:13px; color:#8a6d1a; margin-bottom:16px; }
</style>
</head>
<body>
<div class="header">
  <h1>史莱姆团 · 报名查询</h1>
  <p>查询你填了哪个车表 · 在哪个队 · 打什么位置</p>
</div>
<div class="container">
  <div class="search-box">
    <input id="kw" placeholder="输入游戏ID 或 QQ号，回车查询" autocomplete="off">
    <button onclick="doQuery()">查询</button>
  </div>
  <div class="tip">提示：数据来自各车表名单，如名单有变动请点下方"刷新数据"；查询结果如有遗漏说明该名单暂无法访问。</div>
  <div id="status" class="status"></div>
  <div id="results"></div>
  <div style="text-align:center; margin-top:16px;">
    <button onclick="rebuild()" style="padding:10px 20px; font-size:14px; border:none; border-radius:8px; background:#52c41a; color:#fff; cursor:pointer;">刷新数据</button>
  </div>
  <div class="hint">数据刷新需约1-2分钟（逐个读取各车表名单）</div>
</div>
<script>
function doQuery() {
  var kw = document.getElementById('kw').value.trim();
  if (!kw) return;
  document.getElementById('status').textContent = '查询中...';
  document.getElementById('results').innerHTML = '';
  fetch('/api/query?kw=' + encodeURIComponent(kw))
    .then(r => r.json())
    .then(data => render(kw, data))
    .catch(e => { document.getElementById('status').textContent = '查询出错: ' + e; });
}
function render(kw, data) {
  var s = document.getElementById('status');
  if (data.error) { s.textContent = data.error; return; }
  s.textContent = '共找到 ' + data.total + ' 条记录';
  var box = document.getElementById('results');
  box.innerHTML = '';
  data.results.forEach(function(r) {
    var div = document.createElement('div');
    div.className = 'result';
    div.innerHTML = '<div class="car">' + esc(r.car) + '</div>'
      + '<div class="meta">' + esc(r.time) + '  ·  车头 ' + esc(r.leader) + '</div>'
      + '<div class="info">'
      + '<span><b>玩家:</b> ' + esc(r.name) + '</span>'
      + '<span><b>QQ:</b> ' + esc(r.qq) + '</span>'
      + '<span><b>位置:</b> ' + esc(r.jobs) + '</span>'
      + '<span class="badge">' + esc(r.team) + '</span>'
      + '</div>'
      + '<div style="margin-top:10px;"><a href="' + esc(r.url) + '" target="_blank" style="display:inline-block; background:#667eea; color:#fff; padding:6px 14px; border-radius:6px; text-decoration:none; font-size:13px;">打开该车表名单 →</a></div>';
    box.appendChild(div);
  });
  if (data.results.length === 0) { s.textContent = '未找到 " ' + kw + ' " 的报名记录'; }
}
function rebuild() {
  var s = document.getElementById('status');
  s.textContent = '正在刷新数据（约1-2分钟），请稍候...';
  document.getElementById('results').innerHTML = '';
  fetch('/api/rebuild')
    .then(r => r.json())
    .then(d => { s.textContent = d.msg; })
    .catch(e => { s.textContent = '刷新失败: ' + e; });
}
function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
document.getElementById('kw').addEventListener('keydown', function(e){ if(e.key==='Enter') doQuery(); });
</script>
</body>
</html>
"""


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
            return
        if u.path == "/api/query":
            qs = parse_qs(u.query)
            kw = unquote(qs.get("kw", [""])[0]).strip()
            self.handle_query(kw)
            return
        if u.path == "/api/rebuild":
            self.handle_rebuild()
            return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404")

    def handle_query(self, kw):
        db = load_db()
        if db is None:
            self.send_json({"error": "数据库未生成，请先点击刷新数据"})
            return
        results = []
        for roster in db:
            for p in roster.get("players", []):
                if p.get("qq") == kw or (p.get("name") and kw in p["name"]):
                    results.append({
                        "car": roster.get("label") or roster.get("time") or "?",
                        "time": roster.get("time") or "",
                        "leader": roster.get("leader") or "",
                        "name": p.get("name", ""),
                        "qq": p.get("qq", ""),
                        "jobs": qr.fmt_jobs(p),
                        "team": qr.team_of(p),
                        "url": f"https://docs.qq.com/sheet/{roster.get('doc','')}?tab={roster.get('tab','')}",
                    })
        # 只保留未过期的, 按日期正序排列(早的在前)
        results = [r for r in results if qr.is_upcoming(r.get("time", ""))]
        results.sort(key=lambda x: qr.time_sort_key(x.get("time", "")))
        self.send_json({"total": len(results), "results": results})

    def handle_rebuild(self):
        def run():
            try:
                db = qr.build_database()
                print("[web] 数据库已刷新")
            except Exception as e:
                print("[web] 刷新失败:", e)
        threading.Thread(target=run, daemon=True).start()
        self.send_json({"msg": "开始刷新数据（约1-2分钟）..."})

    def send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    # 确保数据库存在
    if not os.path.exists(DB_FILE):
        print("首次运行，正在生成数据库...")
        try:
            qr.build_database()
        except Exception as e:
            print("数据库生成失败:", e)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"查询网页已启动: http://localhost:{PORT}")
    print("本机其他设备访问: http://<本机IP>:%d" % PORT)
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()
