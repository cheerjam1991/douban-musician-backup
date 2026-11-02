#!/usr/bin/env python3
"""Command-line entry. Most people should use the GUI app instead."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backup_core import BackupError, run_backup
from cookies_from_browser import CookieReadError, read_douban_cookie


def main() -> None:
    parser = argparse.ArgumentParser(description="备份豆瓣音乐人小站音频")
    parser.add_argument("--site", required=True, help="https://site.douban.com/你的slug/")
    parser.add_argument("--cookie", help="Cookie 字符串")
    parser.add_argument("--cookie-file", help="Cookie 文本文件")
    parser.add_argument("--from-browser", action="store_true", help="从本机 Chrome 读取登录")
    parser.add_argument("--out", default="", help="输出目录")
    args = parser.parse_args()

    cookie = ""
    if args.from_browser:
        try:
            cookie, name = read_douban_cookie()
            print(f"已从 {name} 读取登录", file=sys.stderr)
        except CookieReadError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
    elif args.cookie:
        cookie = args.cookie
    elif args.cookie_file:
        cookie = Path(args.cookie_file).read_text(encoding="utf-8")
    else:
        print("请使用 --from-browser，或 --cookie-file / --cookie", file=sys.stderr)
        sys.exit(1)

    try:
        run_backup(args.site, cookie, args.out or None, log=print)
    except BackupError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
