# 豆瓣音乐人备份

把豆瓣音乐人小站里「只有自己登录才看得到」的歌，备份下载。

## 两种用法

| 方式 | 适合谁 | 说明 |
|------|--------|------|
| **在线网站**（本 README 主要讲这个） | 自己 + 朋友，打开网址就能用 | 免费部署到 Render，得到 `xxx.onrender.com` 网址 |
| 桌面版 | 只在你自己电脑上用 | 见文件 `backup_gui.py` / `给朋友的说明.txt` |

## 在线网站：部署到 Render（免费）

### 1. 把代码推到 GitHub

```bash
git init
git add .
git commit -m "douban musician backup web app"
git branch -M main
git remote add origin https://github.com/你的用户名/douban-musician-backup.git
git push -u origin main
```

> 建议用**私有仓库**，虽然代码里没有秘密，但把项目公开也没问题。

### 2. 在 Render 上部署

1. 打开 https://render.com 用 GitHub 账号注册/登录（免费档**不需要**绑信用卡）
2. 点 **New → Blueprint**，选这个仓库，Render 会自动读取 `render.yaml`
3. 点 **Apply**，等它构建完（几分钟）
4. 构建完你会得到一个网址，例如 `https://douban-musician-backup.onrender.com`

### 3. 改访问密码（强烈建议）

在 Render 项目的 **Environment** 里把 `SITE_PASSWORD` 从默认的 `douban` 改成你自己的密码，然后 **redeploy**。

### 4. 使用

打开网址 → 输访问密码 → 按页面说明从浏览器复制 Cookie → 贴小站地址 → 点「开始备份」→ 完成后下载 zip。

> 免费档限制：闲置约 15 分钟后会「睡眠」，下次打开要等几十秒；备份完请及时把 zip 下载到电脑，服务器会定期清理文件。

## 本机跑起来（开发调试）

```bash
python3 -m venv .venv-web
. .venv-web/bin/activate
pip install -r requirements-web.txt
SITE_PASSWORD=douban python webapp.py
# 打开 http://127.0.0.1:8000
```

## 安全说明

- 网站有访问密码，陌生人进不来
- Cookie 只存内存，不写日志、不落盘，任务结束即清
- Cookie 只允许发给 `*.douban.com` / `*.doubanio.com`，其他域名一律拒绝（防止登录凭证外泄）
- 同一时间只跑一个备份任务，防刷

## 桌面版（旧的，仍可用）

给不懂代码的朋友：发 `dist` 里打好的应用 + `给朋友的说明.txt`。

```bash
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --windowed --onefile \
  --name "豆瓣音乐人备份" \
  --collect-all browser_cookie3 \
  backup_gui.py
```

- Mac 得到 `dist/豆瓣音乐人备份.app`
- Windows 上再打一次才能得到 `.exe`

## 命令行（可选）

```bash
python3 backup_douban_musician.py --site https://site.douban.com/xxx/ --from-browser
```
