"""Read Douban login cookies from a local browser. Optional dependency: browser_cookie3."""

from __future__ import annotations


class CookieReadError(Exception):
    pass


def cookie_header_from_jar(jar) -> str:
    parts = []
    seen = set()
    for c in jar:
        host = (c.domain or "").lstrip(".")
        if "douban" not in host:
            continue
        key = (c.name, c.domain, c.path)
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"{c.name}={c.value}")
    # Prefer later duplicates by name: keep last dbcl2
    merged: dict[str, str] = {}
    for p in parts:
        k, _, v = p.partition("=")
        merged[k] = f"{k}={v}"
    header = "; ".join(merged.values())
    if "dbcl2=" not in header:
        raise CookieReadError("浏览器里没有豆瓣登录信息。请先用 Chrome 打开 douban.com 并登录。")
    return header


def read_douban_cookie() -> tuple[str, str]:
    try:
        import browser_cookie3
    except ImportError as e:
        raise CookieReadError("当前版本未包含自动读取功能，请改用手动粘贴 Cookie。") from e

    errors = []
    for name, fn in (
        ("Chrome", getattr(browser_cookie3, "chrome", None)),
        ("Edge", getattr(browser_cookie3, "edge", None)),
        ("Chromium", getattr(browser_cookie3, "chromium", None)),
        ("Firefox", getattr(browser_cookie3, "firefox", None)),
        ("Safari", getattr(browser_cookie3, "safari", None)),
    ):
        if fn is None:
            continue
        try:
            jar = fn(domain_name="douban.com")
            header = cookie_header_from_jar(jar)
            return header, name
        except CookieReadError:
            errors.append(f"{name}：未登录豆瓣")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}：{e}")
    raise CookieReadError(
        "没法从浏览器自动读取登录。\n"
        "请先用 Chrome 打开 https://www.douban.com 并登录，然后点「允许」钥匙串权限。\n"
        + "\n".join(errors)
    )
