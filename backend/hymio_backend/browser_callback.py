"""Return only a one-time confirmation to the initiating client."""

import json
from urllib.parse import urlencode, urlsplit

from starlette.responses import HTMLResponse, RedirectResponse


def browser_callback(return_uri, *, grant=None, error=None):
    result = {"error": "login_failed"} if error else {"login_code": grant}
    if (
        return_uri.startswith("http://127.0.0.1:")
        and urlsplit(return_uri).path == "/hymio-callback"
    ):
        return RedirectResponse(return_uri + "?" + urlencode(result), 303)
    payload = json.dumps({"type": "hymio.login", **result}).replace("<", "\\u003c")
    origin = json.dumps(return_uri).replace("<", "\\u003c")
    title = "登录未完成" if error else "已登录 Hymio"
    return HTMLResponse(
        '<!doctype html><meta charset="utf-8"><title>Hymio</title>'
        "<style>body{font:18px system-ui;max-width:480px;margin:20vh auto;"
        f"padding:24px;color:#253149}}</style><h1>{title}</h1>"
        "<p>可以关闭此窗口，回到应用继续。</p><script>"
        f"if(window.opener)window.opener.postMessage({payload},{origin});"
        "</script>"
    )
