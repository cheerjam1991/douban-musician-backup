#!/usr/bin/env python3
"""Double-clickable backup tool: opens a local webpage, no coding required."""

from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backup_core import BackupError, run_backup, site_slug_and_base
from cookies_from_browser import CookieReadError, read_douban_cookie

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>豆瓣音乐人备份</title>
<style>
  body { font-family: -apple-system, "PingFang SC", sans-serif; max-width: 720px;
         margin: 32px auto; padding: 0 20px; color: #222; }
  h1 { font-size: 22px; }
  label { display: block; margin: 16px 0 6px; font-weight: 600; }
  input, textarea { width: 100%; box-sizing: border-box; padding: 10px; font-size: 15px;
                    border: 1px solid #ccc; border-radius: 8px; }
  textarea { min-height: 90px; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  button { margin: 8px 8px 0 0; padding: 10px 16px; font-size: 15px; border: 0;
           border-radius: 8px; background: #2d6a4f; color: #fff; cursor: pointer; }
  button.secondary { background: #555; }
  button:disabled { opacity: .5; cursor: default; }
  .help { background: #f6f6f6; padding: 14px 16px; border-radius: 8px; line-height: 1.55; }
  #log { white-space: pre-wrap; background: #111; color: #d8f3dc; padding: 12px;
         border-radius: 8px; min-height: 180px; font-size: 13px; }
  .ok { color: #2d6a4f; }
  .err { color: #9b2226; }
</style>
</head>
<body>
<h1>豆瓣音乐人备份</h1>
<p>把小站里只有自己登录才看得到的歌，下载到电脑「下载」文件夹。</p>

<label>小站地址</label>
<input id="site" placeholder="https://site.douban.com/你的英文名/">

<label>保存到</label>
<input id="out" value="__OUT__">

<p>
  <button class="secondary" onclick="openLogin()">打开豆瓣登录页</button>
  <button class="secondary" onclick="readCookie()">自动读取登录</button>
  <button id="go" onclick="startBackup()">开始备份</button>
  <button class="secondary" onclick="quitApp()">退出</button>
</p>
<p id="cookieStatus"></p>

<label>登录信息（自动读取失败再粘贴 Cookie）</label>
<textarea id="cookie" placeholder="一般不用填"></textarea>

<div class="help">
  <b>怎么用</b><br>
  1. 点「打开豆瓣登录页」，用你自己的音乐人账号登录<br>
  2. 把小站地址贴进来<br>
  3. 点「自动读取登录」（若弹出权限窗口，点允许）<br>
  4. 点「开始备份」<br><br>
  读不到登录时：Chrome 打开自己的小站 → 按 F12 → 点「网络」→ 刷新
  → 点最上面一条 → 找到 Cookie → 全选复制 → 粘贴到上面。
</div>

<label>进度</label>
<div id="log"></div>

<script>
function log(t){ const el=document.getElementById('log'); el.textContent += t+'\n'; el.scrollTop=el.scrollHeight; }
async function openLogin(){
  await fetch('/api/open-login');
  log('已打开豆瓣。请在浏览器里登录，再点「自动读取登录」。');
}
async function readCookie(){
  const r = await fetch('/api/read-cookie');
  const j = await r.json();
  const st = document.getElementById('cookieStatus');
  if(j.ok){
    document.getElementById('cookie').value = j.cookie;
    st.className='ok'; st.textContent='已从 '+j.browser+' 读取到登录，可以开始备份。';
    log('已从 '+j.browser+' 读取登录。');
  } else {
    st.className='err'; st.textContent=j.error;
    log(j.error);
  }
}
async function startBackup(){
  const btn=document.getElementById('go');
  btn.disabled=true;
  document.getElementById('log').textContent='';
  const body = {
    site: document.getElementById('site').value,
    cookie: document.getElementById('cookie').value,
    out: document.getElementById('out').value
  };
  const r = await fetch('/api/backup', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json();
  if(!j.ok){ log(j.error||'启动失败'); btn.disabled=false; return; }
  poll();
}
async function quitApp(){
  await fetch('/api/quit');
  document.body.innerHTML = '<p style="padding:40px">已退出，可以关掉这个页面。</p>';
}
async function poll(){
  const r = await fetch('/api/log');
  const j = await r.json();
  document.getElementById('log').textContent = j.lines.join('\n');
  if(!j.done){ setTimeout(poll, 400); return; }
  document.getElementById('go').disabled=false;
  if(j.error) log('\\n失败：'+j.error);
}
</script>
</body>
</html>
"""

_state_lock = threading.Lock()
_state = {
    "lines": [],
    "done": True,
    "error": "",
    "dest": "",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = PAGE.replace("__OUT__", str(Path.home() / "Downloads"))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/open-login":
            webbrowser.open("https://www.douban.com/")
            self._json({"ok": True})
            return
        if path == "/api/read-cookie":
            try:
                header, browser = read_douban_cookie()
                self._json({"ok": True, "cookie": header, "browser": browser})
            except CookieReadError as e:
                self._json({"ok": False, "error": str(e)})
            return
        if path == "/api/quit":
            self._json({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
            return
        if path == "/api/log":
            with _state_lock:
                self._json(
                    {
                        "lines": list(_state["lines"]),
                        "done": _state["done"],
                        "error": _state["error"],
                        "dest": _state["dest"],
                    }
                )
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/backup":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            data = parse_qs(raw.decode("utf-8"))
            data = {k: v[0] if isinstance(v, list) else v for k, v in data.items()}
        site = (data.get("site") or "").strip()
        cookie = (data.get("cookie") or "").strip()
        out_root = (data.get("out") or str(Path.home() / "Downloads")).strip()
        try:
            slug, _ = site_slug_and_base(site)
        except BackupError as e:
            self._json({"ok": False, "error": str(e)})
            return
        if not cookie:
            self._json({"ok": False, "error": "还没登录。请先点「自动读取登录」，或粘贴 Cookie。"})
            return
        out_dir = str(Path(out_root) / f"豆瓣音乐人_{slug}")
        with _state_lock:
            if not _state["done"]:
                self._json({"ok": False, "error": "正在备份，请等当前任务结束。"})
                return
            _state.update({"lines": ["开始备份…"], "done": False, "error": "", "dest": ""})

        def work() -> None:
            def log(msg: str) -> None:
                with _state_lock:
                    _state["lines"].append(msg)

            try:
                dest = run_backup(site, cookie, out_dir, log=log)
                with _state_lock:
                    _state["dest"] = str(dest)
            except BackupError as e:
                with _state_lock:
                    _state["error"] = str(e)
                    _state["lines"].append(str(e))
            except Exception as e:  # noqa: BLE001
                with _state_lock:
                    _state["error"] = str(e)
                    _state["lines"].append(f"出错：{e}")
            finally:
                with _state_lock:
                    _state["done"] = True

        threading.Thread(target=work, daemon=True).start()
        self._json({"ok": True})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webbrowser.open(url)
    print(f"已打开备份页面：{url}")
    print("关掉这个窗口就会停止程序。")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
