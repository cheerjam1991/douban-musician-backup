# 豆瓣音乐人备份（Mac 桌面版）

把豆瓣音乐人小站里「只有自己登录才看得到」的歌，备份到电脑。

给不懂代码的朋友：发 `dist` 里打好的应用 + `给朋友的说明.txt`。

## 打包（Mac）

```bash
cd douban-musician-backup
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --windowed --onefile \
  --name "豆瓣音乐人备份" \
  --collect-all browser_cookie3 \
  backup_gui.py
```

- Mac 得到 `dist/豆瓣音乐人备份.app`（或同名可执行文件）
- 必须在 **Windows 电脑**上再打一次，才能得到 `.exe`（Mac 打不出 Windows 程序）

## 命令行（可选）

```bash
python3 backup_douban_musician.py --site https://site.douban.com/xxx/ --from-browser
```

## 本机直接跑（不打包，开发调试）

```bash
python3 backup_gui.py          # 图形窗口版
# 或
python3 backup_app.py          # 双击弹网页版
```

> 在线网站版在 `main` 分支，这里（`mac-desktop`）只放桌面版。
