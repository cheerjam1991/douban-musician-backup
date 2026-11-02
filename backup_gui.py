#!/usr/bin/env python3
"""Simple window for backing up a Douban musician site. Double-click the packaged app."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from backup_core import BackupError, run_backup, site_slug_and_base
from cookies_from_browser import CookieReadError, read_douban_cookie

HELP = """请按顺序做：

1. 用电脑上的 Chrome 打开 https://www.douban.com 并登录
   （必须是小站主人自己的账号）
2. 把小站地址贴到上面，例如
   https://site.douban.com/你的英文名/
3. 点「自动读取登录」
   若弹出钥匙串/权限窗口，点允许
4. 点「开始备份」

读不到登录时：在 Chrome 打开自己的小站 → 按 F12 → 点「网络」
→ 刷新页面 → 点最上面一条 → 右侧找到 Cookie → 全选复制
→ 粘贴到「登录信息」框。
"""


def default_out() -> str:
    return str(Path.home() / "Downloads")


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("豆瓣音乐人备份")
        self.geometry("720x640")
        self.minsize(640, 560)
        self.cookie = ""

        pad = {"padx": 16, "pady": 6}

        ttk.Label(self, text="把豆瓣音乐人小站里的歌备份到电脑", font=("PingFang SC", 16)).pack(
            anchor="w", **pad
        )

        ttk.Label(self, text="小站地址").pack(anchor="w", padx=16)
        self.site_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.site_var, font=("PingFang SC", 13)).pack(
            fill="x", padx=16, pady=(0, 8)
        )

        ttk.Label(self, text="保存到哪个文件夹").pack(anchor="w", padx=16)
        row = ttk.Frame(self)
        row.pack(fill="x", padx=16, pady=(0, 8))
        self.out_var = tk.StringVar(value=default_out())
        ttk.Entry(row, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="选择…", command=self.choose_dir).pack(side="left", padx=(8, 0))

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=16, pady=8)
        ttk.Button(btns, text="打开豆瓣登录页", command=self.open_login).pack(side="left")
        ttk.Button(btns, text="自动读取登录", command=self.auto_cookie).pack(side="left", padx=8)
        self.start_btn = ttk.Button(btns, text="开始备份", command=self.start)
        self.start_btn.pack(side="left")

        ttk.Label(self, text="登录信息（一般不用填，自动读取失败再粘贴 Cookie）").pack(
            anchor="w", padx=16
        )
        self.cookie_box = tk.Text(self, height=5, wrap="word", font=("Menlo", 11))
        self.cookie_box.pack(fill="x", padx=16, pady=(0, 8))

        ttk.Label(self, text="说明", font=("PingFang SC", 12)).pack(anchor="w", padx=16)
        help_box = tk.Text(self, height=9, wrap="word", font=("PingFang SC", 12), bg="#f6f6f6")
        help_box.pack(fill="x", padx=16)
        help_box.insert("1.0", HELP)
        help_box.configure(state="disabled")

        ttk.Label(self, text="进度").pack(anchor="w", padx=16, pady=(8, 0))
        self.log_box = tk.Text(self, height=10, wrap="word", font=("Menlo", 11))
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def log(self, msg: str) -> None:
        def _append() -> None:
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")

        self.after(0, _append)

    def choose_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_var.get() or default_out())
        if d:
            self.out_var.set(d)

    def open_login(self) -> None:
        webbrowser.open("https://www.douban.com/")
        self.log("已打开豆瓣。请在弹出的浏览器里登录，然后回到这里点「自动读取登录」。")

    def typed_cookie(self) -> str:
        return self.cookie_box.get("1.0", "end").strip() or self.cookie

    def auto_cookie(self) -> None:
        try:
            header, browser = read_douban_cookie()
        except CookieReadError as e:
            messagebox.showwarning("没有读到登录", str(e))
            self.log(str(e))
            return
        self.cookie = header
        self.cookie_box.delete("1.0", "end")
        self.cookie_box.insert("1.0", header)
        self.log(f"已从 {browser} 读取到豆瓣登录。")
        messagebox.showinfo("成功", f"已从 {browser} 读取到登录，可以点「开始备份」。")

    def start(self) -> None:
        site = self.site_var.get().strip()
        cookie = self.typed_cookie()
        out_root = self.out_var.get().strip() or default_out()
        if not site:
            messagebox.showwarning("还没填地址", "请粘贴小站地址，例如 https://site.douban.com/xxx/")
            return
        try:
            slug, _ = site_slug_and_base(site)
        except BackupError as e:
            messagebox.showwarning("地址不对", str(e))
            return
        if not cookie:
            messagebox.showwarning("还没登录", "请先点「自动读取登录」，或粘贴 Cookie。")
            return
        out_dir = str(Path(out_root) / f"豆瓣音乐人_{slug}")
        self.start_btn.configure(state="disabled")
        self.log("开始备份…")

        def work() -> None:
            try:
                dest = run_backup(site, cookie, out_dir, log=self.log)
            except BackupError as e:
                self.log(str(e))
                self.after(0, lambda: messagebox.showerror("没能完成", str(e)))
            except Exception as e:  # noqa: BLE001
                self.log(f"出错：{e}")
                self.after(0, lambda: messagebox.showerror("出错", str(e)))
            else:
                def done() -> None:
                    if messagebox.askyesno("完成", f"已经备份到：\n{dest}\n\n打开这个文件夹吗？"):
                        open_folder(dest)

                self.after(0, done)
            finally:
                self.after(0, lambda: self.start_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
