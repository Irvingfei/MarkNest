#!/usr/bin/env python3
"""Loopback development server for the MarkNest WebUI.

The packaged service speaks HTTP over a Unix socket because that is what the TOS
proxy expects. Windows has no AF_UNIX in the Python build this repository is
developed on, so this script serves the same :mod:`lib.api` dispatcher over
loopback TCP and the real ``webui/`` directory next to it.

It is a development tool only: it is never packaged, it injects a fixed user
identity, and it disables platform authentication. Do not deploy it.

Usage:
    python tools/serve_dev_tcp.py            # http://127.0.0.1:8787/
    python tools/serve_dev_tcp.py --port 9000 --reset
"""

import argparse
import http.server
import io
import json
import os
import shutil
import socketserver
import struct
import sys
import threading
import zlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBUI = os.path.join(REPO_ROOT, "webui")
DEMO_ROOT = os.path.join(REPO_ROOT, ".devdata")
SHARE_ROOT = os.path.join(DEMO_ROOT, "share")
USER = "tester"


def configure_environment():
    os.environ["MARKNEST_SHARE_ROOT"] = SHARE_ROOT
    os.environ["MARKNEST_DATA_DIR"] = os.path.join(DEMO_ROOT, "appdata")
    os.environ["MARKNEST_REQUIRE_AUTH"] = "false"
    os.environ["MARKNEST_REQUIRE_SYSTEM_USER"] = "false"
    os.environ["MARKNEST_SCAN_INTERVAL"] = "600"
    os.environ["MARKNEST_LOG_LEVEL"] = os.environ.get("MARKNEST_LOG_LEVEL", "WARNING")
    os.environ.setdefault("MARKNEST_ROOT", os.path.join(REPO_ROOT, "usr", "local", "marknest"))


def _png(width, height, top, bottom):
    """A small vertical-gradient PNG, written without third-party libraries."""
    rows = []
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = bytes(
            int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)
        )
        rows.append(b"\x00" + color * width)
    raw = b"".join(rows)

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


DEMO_NOTES = {
    "欢迎使用 MarkNest.md": """# 欢迎使用 MarkNest

把想法留在这里，文件仍然是普通的 Markdown 文件。它们保存在 NAS 的共享文件夹里，
文件管理器可见、SMB 可访问，也可以由卷快照保留历史。

## 为什么用 MarkNest

- **文件优先**：没有私有格式，离开应用也能打开。
- **专注写作**：工具栏、大纲与实时预览都在同一页。
- **随手插图**：粘贴或拖入图片即可上传。
- **可回溯**：每次保存都会留下版本记录。

> 写作是把思考固定下来的过程。工具应该退到背景里。

## 快捷操作

| 操作 | 快捷键 |
| --- | --- |
| 保存 | `Ctrl / Cmd + S` |
| 全局搜索 | `Ctrl / Cmd + K` |
| 新建笔记 | `Ctrl / Cmd + N` |

```js
const idea = "先写下来，再慢慢变好";
console.log(idea);
```

- [x] 建立自己的笔记库
- [ ] 写下今天最重要的一件事
- [ ] 把零散的片段整理成一篇文档

![MarkNest 主题图](.assets/welcome-cover.png)

祝你写得顺畅。
""",
    "产品/发布清单.md": """# 发布清单

一份可以在每次发布前逐项勾选的清单。

## 发布前

- [ ] 版本号已经递增
- [ ] 变更说明写清楚「为什么」
- [ ] 在真机上走一遍主路径
- [ ] 回滚方案明确到命令

## 发布后

- [ ] 观察错误日志十分钟
- [ ] 确认关键接口的延迟没有上升
- [ ] 把问题记录进下一轮计划

> 清单的价值不在于它写了什么，而在于它每次都逼你停下来看一眼。
""",
    "产品/写作规范.md": """# 写作规范

## 结构

1. 先给结论，再给理由。
2. 每段只承担一个意思。
3. 标题要能独立成句。

## 语言

- 少用「非常」「十分」这类程度词。
- 数字、时间、单位保持精确。
- 引用别人时给出处。

## 排版

标题之间不要跳级；列表只用于并列项；代码块标注语言。
""",
    "项目/路线图.md": """# 2026 路线图

## 第一季度

- 笔记库列表与文件管理
- 编辑器工具栏与大纲
- 图片上传与粘贴

## 第二季度

- 版本历史与恢复
- 导入与导出
- 分享链接

## 长期

让笔记库在 NAS 上安静地生长，而不是变成一个需要维护的系统。
""",
    "灵感/收集箱.md": """# 收集箱

> 先收集，再整理。不要在下班路上要求自己完成结构。

- 读到一半的想法
- 别人随口提到的一本书
- 想改但还没改的段落
- 一个可以做成小工具的点子

清理收集箱时问自己：它值得占用一块注意力吗？
""",
    "灵感/标题的写法.md": """# 标题的写法

标题不是摘要，它是读者决定要不要读下去的那一秒。

## 三个检验

1. 能不能独立成立？
2. 有没有具体名词？
3. 换一个标题，文章还成立吗？

如果第三个问题的答案是「成立」，标题大概还不够准确。
""",
}


def seed_demo():
    sys.path.insert(0, os.path.join(REPO_ROOT, "usr", "local", "marknest"))
    from lib import library

    notes_root = library.user_notes_root(USER)
    existing = []
    for base, _dirs, files in os.walk(notes_root):
        existing.extend(name for name in files if name.lower().endswith(".md"))
    if existing:
        return

    cover_dir = os.path.join(notes_root, ".assets")
    os.makedirs(cover_dir, exist_ok=True)
    with open(os.path.join(cover_dir, "welcome-cover.png"), "wb") as handle:
        handle.write(_png(960, 420, (32, 58, 48), (198, 164, 106)))

    for rel, content in DEMO_NOTES.items():
        library.create_note(USER, rel, content)
    print("seeded %d demo notes in %s" % (len(DEMO_NOTES), notes_root))


class DevHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MarkNestDev/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        if os.environ.get("MARKNEST_DEV_LOUD"):
            super().log_message(*args)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.path.split("?")[0].startswith("/v2/proxy/marknest"):
            self._api(body)
        else:
            self._static(body)

    def _api(self, body):
        from lib.api import api
        from lib.errors import MarkNestError
        from lib.http_util import Headers, RawResponse, wrap_success

        headers = Headers(self.headers.items())
        if not headers.get("X-MarkNest-User"):
            headers.add("X-MarkNest-User", USER)
        from lib.http_util import Request

        request = Request(
            self.command,
            self.path,
            "HTTP/1.1",
            headers,
            io.BytesIO(body),
        )
        try:
            status, payload = api.dispatch(request)
        except MarkNestError as exc:
            status, payload = exc.status, exc.to_payload()
        except Exception as exc:  # noqa: BLE001 - dev server: show the failure
            import traceback

            traceback.print_exc()
            status, payload = 500, {
                "code": 1000, "message": "internal error: %s" % exc, "data": None,
            }
        finally:
            try:
                request.cleanup()
            except Exception:
                pass

        if isinstance(payload, RawResponse):
            self.send_response(payload.status)
            self.send_header("Content-Type", payload.content_type)
            for key, value in payload.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload.body)))
            self.end_headers()
            self.wfile.write(payload.body)
            return

        if status == 204:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if status < 400:
            payload = wrap_success(payload)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, body):
        path = self.path.split("?")[0]
        if path in ("/", ""):
            path = "/index.html"
        target = os.path.normpath(os.path.join(WEBUI, path.lstrip("/")))
        if not target.startswith(os.path.normpath(WEBUI)) or not os.path.isfile(target):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "9")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        with open(target, "rb") as handle:
            data = handle.read()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".json": "application/json; charset=utf-8",
        }
        ext = os.path.splitext(target)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", types.get(ext, "application/octet-stream"))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class DevServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main(argv=None):
    parser = argparse.ArgumentParser(description="MarkNest loopback development server")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reset", action="store_true", help="delete .devdata first")
    args = parser.parse_args(argv)

    if args.reset and os.path.isdir(DEMO_ROOT):
        shutil.rmtree(DEMO_ROOT, ignore_errors=True)
    os.makedirs(SHARE_ROOT, exist_ok=True)
    configure_environment()
    seed_demo()

    server = DevServer((args.host, args.port), DevHandler)
    url = "http://%s:%d/" % (args.host, args.port)
    print("MarkNest dev UI: %s" % url)
    print("share root     : %s" % SHARE_ROOT)
    print("identity       : %s (auth disabled)" % USER)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
