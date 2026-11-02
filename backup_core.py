#!/usr/bin/env python3
"""Download Douban musician tracks visible only to the logged-in site owner."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Cookie 只允许发给这些豆瓣域名，防止登录凭证被带出到别的服务器。
COOKIE_HOSTS = ("douban.com", "doubanio.com")


def _host_allowed(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in COOKIE_HOSTS)


LogFn = Callable[[str], None]


class BackupError(Exception):
    pass


def safe_name(name: str) -> str:
    name = html.unescape(name).strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "untitled"


def http_get(url: str, cookie: str, referer: str, timeout: int = 60) -> bytes:
    if not _host_allowed(url):
        raise BackupError(f"拒绝访问非豆瓣域名（防止 Cookie 外泄）：{url}")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Cookie": cookie,
            "Referer": referer,
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, cookie: str, referer: str) -> str:
    return http_get(url, cookie, referer).decode("utf-8", "ignore")


def site_slug_and_base(site: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(site.strip())
    if parsed.netloc not in ("site.douban.com", "www.site.douban.com"):
        raise BackupError(f"站点地址不对，应为 https://site.douban.com/某音乐人/\n收到：{site}")
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise BackupError("地址不完整。请填 https://site.douban.com/你的英文名/")
    slug = parts[0]
    return slug, f"https://site.douban.com/{slug}/"


def extract_rooms(home_html: str, slug: str) -> list[tuple[str, str]]:
    rooms: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rid, title in re.findall(
        rf'href="https://site\.douban\.com/{re.escape(slug)}/room/(\d+)/"[^>]*>\s*<span>([^<]+)</span>',
        home_html,
    ):
        if rid not in seen:
            seen.add(rid)
            rooms.append((rid, html.unescape(title).strip()))
    for rid in re.findall(rf"/{re.escape(slug)}/room/(\d+)/", home_html):
        if rid not in seen:
            seen.add(rid)
            rooms.append((rid, rid))
    return rooms


def extract_playlists(page: str) -> list[tuple[str, list[dict]]]:
    wid2name: dict[str, str] = {}
    for m in re.finditer(r"<h2>\s*<span>([^<]+)</span>(.*?)(?=<h2>|\Z)", page, re.S):
        ids = re.findall(r"widget/playlist/(\d+)/", m.group(2))
        if ids:
            wid2name[ids[0]] = html.unescape(m.group(1).strip())

    playlists: list[tuple[str, list[dict]]] = []
    used_names: dict[str, int] = {}
    for m in re.finditer(
        r"Song\.config\(\{lyrics_src:\s*\"[^\"]*?widget/playlist/(\d+)/get_song_lyrics\".*?song_records\s*=\s*(\[.*?\])\s*,",
        page,
        re.S,
    ):
        wid, raw = m.group(1), m.group(2)
        try:
            songs = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(songs, list):
            continue
        name = wid2name.get(wid, f"playlist_{wid}")
        n = used_names.get(name, 0) + 1
        used_names[name] = n
        if n > 1:
            name = f"{name}_{n}"
        playlists.append((name, songs))
    return playlists


def download_mp3(url: str, dest: Path, cookie: str, referer: str, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for i in range(retries):
        try:
            data = http_get(url, cookie, referer)
            if len(data) < 1000:
                raise RuntimeError(f"文件过小（{len(data)} bytes），可能不是音频")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1 + i)
    raise RuntimeError(last_err)


def normalize_cookie(text: str) -> str:
    text = text.strip()
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    return " ".join(text.split())


def run_backup(
    site: str,
    cookie: str,
    out_dir: str | Path | None = None,
    log: LogFn | None = None,
) -> Path:
    def say(msg: str) -> None:
        if log:
            log(msg)

    cookie = normalize_cookie(cookie)
    if "dbcl2=" not in cookie:
        raise BackupError("还没登录成功。请先用浏览器登录豆瓣，再点「自动读取登录」或粘贴 Cookie。")

    slug, base = site_slug_and_base(site)
    out = Path(out_dir).expanduser() if out_dir else Path.home() / "Downloads" / f"豆瓣音乐人_{slug}"
    out.mkdir(parents=True, exist_ok=True)

    say(f"小站：{base}")
    say(f"保存到：{out}")

    try:
        home = fetch_text(base, cookie, base)
    except urllib.error.HTTPError as e:
        raise BackupError(f"打开小站失败 HTTP {e.code}：{e.reason}") from e
    except urllib.error.URLError as e:
        raise BackupError(f"打开小站失败：{e.reason}") from e

    if 'name="form_email"' in home and "login" in home.lower():
        raise BackupError("登录已过期。请重新登录豆瓣后再试。")

    rooms = extract_rooms(home, slug)
    say(f"发现 {len(rooms)} 个房间" if rooms else "未解析到房间，改为扫描首页。")
    pages: list[tuple[str, str]] = list(rooms) or [("home", slug)]

    manifest: list[dict] = []
    ok = skip = fail = 0
    empty_rawurl = False

    for rid, title in pages:
        url = base if rid == "home" else f"{base}room/{rid}/"
        say(f"\n房间：{title}")
        try:
            page = fetch_text(url, cookie, base)
        except Exception as e:  # noqa: BLE001
            say(f"  打开失败：{e}")
            fail += 1
            continue
        if '"url":""' in page and '"rawUrl":""' in page and "song_records" in page:
            empty_rawurl = True
            say("  看到歌曲，但没有下载地址：当前登录不是这个小站的主人。")
        playlists = extract_playlists(page)
        if not playlists:
            say("  这个房间没有可下载的歌曲。")
            continue
        room_dir = safe_name(title)
        for album, songs in playlists:
            say(f"  播放列表「{album}」：{len(songs)} 首")
            for idx, song in enumerate(songs, 1):
                name = song.get("name") or f"song_{song.get('id')}"
                raw = (song.get("rawUrl") or "").replace("\\/", "/")
                rec = {
                    "room": title,
                    "room_id": rid,
                    "album": album,
                    "id": song.get("id"),
                    "name": name,
                    "rawUrl": raw,
                }
                if not raw:
                    rec["status"] = "NO_URL"
                    manifest.append(rec)
                    fail += 1
                    say(f"    无地址：{name}")
                    continue
                dest = out / room_dir / safe_name(album) / f"{idx:02d} - {safe_name(name)}.mp3"
                rec["file"] = str(dest)
                if dest.exists() and dest.stat().st_size > 1000:
                    rec["status"] = "exists"
                    manifest.append(rec)
                    skip += 1
                    say(f"    已有，跳过：{dest.name}")
                    continue
                try:
                    download_mp3(raw, dest, cookie, url)
                    rec["status"] = f"ok {dest.stat().st_size} bytes"
                    ok += 1
                    say(f"    完成：{dest.name}")
                except Exception as e:  # noqa: BLE001
                    rec["status"] = f"ERR {e}"
                    fail += 1
                    say(f"    失败：{name}（{e}）")
                manifest.append(rec)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    say(f"\n完成：新下载 {ok} 首，跳过 {skip} 首，失败 {fail} 首")
    say(f"文件夹：{out}")
    if ok + skip == 0:
        extra = "请确认登录的是小站主人账号。" if empty_rawurl else "请确认小站里有播放列表。"
        raise BackupError(f"没有下到任何文件。{extra}")
    return out
