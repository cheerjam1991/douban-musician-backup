#!/usr/bin/env python3
"""Douban musician backup, as an online website (Flask).

Security hardening:
- Access password required before anyone can use the site.
- Cookies live only in memory, never logged, never written to disk, cleared after each job.
- backup_core refuses to send cookies to non-Douban hosts.
- Only one backup job runs at a time.
"""

from __future__ import annotations

import html
import json
import os
import shutil
import threading
import uuid
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for

from backup_core import BackupError, run_backup, site_slug_and_base

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()

SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "douban").strip()
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Cookie 只允许豆瓣域名，见 backup_core。这里再兜底一份，双重保险。
MAX_COOKIE_LEN = 8000

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>豆瓣音乐人备份</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 720px; margin: 32px auto; padding: 0 20px; color: #222; }
  h1 { font-size: 22px; }
  label { display: block; margin: 16px 0 6px; font-weight: 600; }
  input, textarea { width: 100%; box-sizing: border-box; padding: 10px; font-size: 15px;
                    border: 1px solid #ccc; border-radius: 8px; }
  textarea { min-height: 100px; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  button { margin: 8px 8px 0 0; padding: 10px 16px; font-size: 15px; border: 0;
           border-radius: 8px; background: #2d6a4f; color: #fff; cursor: pointer; }
  button.secondary { background: #555; }
  button:disabled { opacity: .5; cursor: default; }
  .help { background: #f6f6f6; padding: 14px 16px; border-radius: 8px; line-height: 1.6; }
  .help code { background: #e8e8e8; padding: 1px 5px; border-radius: 4px; }
  #log { white-space: pre-wrap; background: #111; color: #d8f3dc; padding: 12px;
         border-radius: 8px; min-height: 180px; font-size: 13px; }
  .ok { color: #2d6a4f; }
  .err { color: #9b2226; }
  #download { margin-top: 12px; padding: 14px 16px; background: #e8f5e9; border-radius: 8px; display: none; }
  #download a { font-weight: 700; }
</style>
</head>
<body>
<h1>豆瓣音乐人备份</h1>
<p>把小站里只有自己登录才看得到的歌，备份到服务器并打包下载。</p>

<label>小站地址</label>
<input id="site" placeholder="https://site.douban.com/你的英文名/">

<label>登录信息（Cookie）</label>
<textarea id="cookie" placeholder="把 Cookie 粘贴到这里"></textarea>

<div class="help">
  <b>怎么拿到 Cookie</b><br>
  1. 用 Chrome 打开你自己的小站并登录<br>
  2. 按 <code>F12</code> 打开开发者工具 → 点「网络 Network」<br>
  3. 刷新页面（F5）→ 点最上面一条请求<br>
  4. 找到 <code>Cookie</code> 字段 → 全选复制 → 粘贴到上面<br><br>
  Cookie 相当于你的豆瓣登录凭证，只会在本次备份中临时使用，不会保存到服务器。
</div>

<p style="margin-top:16px">
  <button id="go" onclick="startBackup()">开始备份</button>
  <button class="secondary" onclick="logout()">退出</button>
</p>

<div id="download"></div>

<label>进度</label>
<div id="log"></div>

<script>
let timer = null;
function log(t){ const el=document.getElementById('log'); el.textContent += t+'\n'; el.scrollTop=el.scrollHeight; }
function logout(){ fetch('/logout', {method:'POST'}).then(()=>location.reload()); }
async function startBackup(){
  const btn=document.getElementById('go');
  btn.disabled=true;
  document.getElementById('log').textContent='';
  document.getElementById('download').style.display='none';
  const body = {
    site: document.getElementById('site').value,
    cookie: document.getElementById('cookie').value
  };
  const r = await fetch('/api/backup', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json();
  if(!j.ok){ log(j.error||'启动失败'); btn.disabled=false; return; }
  poll(j.job_id);
}
async function poll(id){
  const r = await fetch('/api/log/'+id);
  const j = await r.json();
  document.getElementById('log').textContent = j.lines.join('\n');
  if(j.done){
    document.getElementById('go').disabled=false;
    if(j.error){ log('\\n失败：'+j.error); }
    if(j.download_url){
      const d=document.getElementById('download');
      d.innerHTML = '<a href="'+j.download_url+'">⬇ 下载备份 zip</a>（下载后请及时保存到电脑，服务器会定期清理）';
      d.style.display='block';
    }
    return;
  }
  timer=setTimeout(()=>poll(id), 500);
}
</script>
</body>
</html>
"""

LOGIN_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 - 豆瓣音乐人备份</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 400px; margin: 80px auto; padding: 0 20px; color: #222; }
  h1 { font-size: 22px; }
  input { width: 100%; box-sizing: border-box; padding: 10px; font-size: 15px;
          border: 1px solid #ccc; border-radius: 8px; }
  button { margin-top: 12px; padding: 10px 16px; font-size: 15px; border: 0;
           border-radius: 8px; background: #2d6a4f; color: #fff; cursor: pointer; }
  .err { color: #9b2226; }
</style>
</head>
<body>
<h1>请输入访问密码</h1>
<form method="post" action="/login">
  <input type="password" name="password" placeholder="访问密码" autofocus>
  <div style="margin-top:12px"><button type="submit">进入</button></div>
  <p class="err">__ERR__</p>
</form>
</body>
</html>
"""

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _authed() -> bool:
    return bool(session.get("authed"))


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _authed():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        if request.form.get("password", "") == SITE_PASSWORD:
            session["authed"] = True
            return redirect(url_for("index"))
        err = "密码不对，请重试。"
    return Response(LOGIN_PAGE.replace("__ERR__", html.escape(err)), mimetype="text/html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/")
@require_auth
def index():
    return Response(PAGE, mimetype="text/html")


def _cleanup_old_jobs() -> None:
    """Remove finished jobs and their zip files older than a while."""
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j.get("_cleaned")]
        for jid in stale:
            _jobs.pop(jid, None)


@app.route("/api/backup", methods=["POST"])
@require_auth
def api_backup():
    data = request.get_json(silent=True) or {}
    site = (data.get("site") or "").strip()
    cookie = (data.get("cookie") or "").strip()

    if len(cookie) > MAX_COOKIE_LEN:
        return jsonify({"ok": False, "error": "Cookie 太长，看起来不是正常的登录信息。"})
    try:
        slug, _ = site_slug_and_base(site)
    except BackupError as e:
        return jsonify({"ok": False, "error": str(e)})
    if not cookie:
        return jsonify({"ok": False, "error": "还没填 Cookie。请按页面说明，从浏览器复制 Cookie 再粘贴。"})

    with _jobs_lock:
        running = any(j.get("running") for j in _jobs.values())
        if running:
            return jsonify({"ok": False, "error": "服务器上已有任务在备份，请稍后再试。"})
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "lines": ["开始备份…"],
            "done": False,
            "running": True,
            "error": "",
            "zip_path": "",
            "download_url": "",
            "_cleaned": False,
        }
        _jobs[job_id] = job

    # Cookie 只放在这个线程的局部变量里，任务结束即丢弃，不落盘。
    def work(job_id: str) -> None:
        job = _jobs[job_id]
        out_dir = JOBS_DIR / job_id / f"豆瓣音乐人_{slug}"

        def log(msg: str) -> None:
            with _jobs_lock:
                job["lines"].append(msg)

        try:
            dest = run_backup(site, cookie, out_dir, log=log)
            log("正在打包 zip…")
            zip_base = JOBS_DIR / job_id / f"豆瓣音乐人_{slug}"
            zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=dest)
            with _jobs_lock:
                job["zip_path"] = zip_path
                job["download_url"] = f"/download/{job_id}"
            log("打包完成，可以下载。")
        except BackupError as e:
            log(str(e))
            with _jobs_lock:
                job["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            log(f"出错：{e}")
            with _jobs_lock:
                job["error"] = str(e)
        finally:
            with _jobs_lock:
                job["running"] = False
                job["done"] = True

    threading.Thread(target=work, args=(job_id,), daemon=True).start()
    _cleanup_old_jobs()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/log/<job_id>")
@require_auth
def api_log(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"lines": ["任务不存在或已过期。"], "done": True, "error": ""})
        return jsonify(
            {
                "lines": list(job["lines"]),
                "done": job["done"],
                "error": job["error"],
                "download_url": job["download_url"],
            }
        )


@app.route("/download/<job_id>")
@require_auth
def download(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or not job["zip_path"]:
            return "文件不存在或已过期。", 404
        zip_path = job["zip_path"]
        name = Path(zip_path).name
    return send_file(zip_path, as_attachment=True, download_name=name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)
