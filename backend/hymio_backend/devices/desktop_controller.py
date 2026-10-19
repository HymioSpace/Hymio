"""Executed inside the desktop. No product credentials enter this process."""

import base64
import os
import signal
import subprocess
import tempfile
import time


class OperationRejected(ValueError):
    pass


def shell(command, cwd, timeout):
    started = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            ["bash", "-lc", "ulimit -f 8192; " + command],
            cwd=cwd,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Do not leave background descendants mutating the desktop after releasing its lock.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        streams = []
        truncated = False
        for stream in (out, err):
            size = stream.tell()
            stream.seek(0)
            head = stream.read(32768)
            stream.seek(max(32768, size - 32768))
            tail = stream.read(32768) if size > 32768 else b""
            truncated |= size > 65536
            streams.append(
                (head + (b"\n[truncated]\n" if size > 65536 else b"") + tail).decode(
                    "utf-8", "replace"
                )
            )
    return dict(
        exit_code=None if timed_out else process.returncode,
        stdout=streams[0],
        stderr=streams[1],
        duration_ms=round((time.monotonic() - started) * 1000),
        timed_out=timed_out,
        truncated=truncated,
    )


def browser(args, timeout):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        connected = playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:9222", timeout=timeout * 1000
        )
        context = connected.contexts[0]
        if not context.pages:
            context.new_page()

        def page_id(page):
            session = context.new_cdp_session(page)
            try:
                return session.send("Target.getTargetInfo")["targetInfo"]["targetId"]
            finally:
                session.detach()

        pages = {page_id(page): page for page in context.pages}
        action = args["action"]
        if action == "tabs":
            result = {
                "tabs": [
                    {"page_id": key, "url": item.url, "title": item.title()}
                    for key, item in pages.items()
                ]
            }
            connected.close()
            return result
        target = args.get("page_id")
        if target and target not in pages:
            raise OperationRejected("page_id no longer exists; use tabs to select a current page")
        page = (
            pages[target]
            if target
            else next(
                (item for item in pages.values() if item.evaluate("document.hasFocus()")),
                context.pages[0],
            )
        )
        if action == "new_tab":
            page = context.new_page()
        if action == "close_tab":
            page.close()
            page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(timeout * 1000)
        page.bring_to_front()
        subprocess.run(
            [
                "xdotool",
                "search",
                "--onlyvisible",
                "--class",
                "google-chrome|chromium",
                "windowactivate",
                "--sync",
            ],
            check=True,
            timeout=min(3, timeout),
            capture_output=True,
        )
        if action == "navigate" or action == "new_tab" and args.get("url"):
            if not args["url"].startswith(("https://", "http://")):
                raise ValueError("Expected HTTP(S) URL")
            page.goto(args["url"], wait_until="domcontentloaded", timeout=timeout * 1000)
        elif action == "click":
            page.locator(args["selector"]).click()
        elif action == "fill":
            page.locator(args["selector"]).fill(args["text"])
        elif action == "key":
            page.keyboard.press(args["key"])
        elif action in ("back", "forward", "reload"):
            method = {"back": page.go_back, "forward": page.go_forward, "reload": page.reload}[
                action
            ]
            method(wait_until="domcontentloaded", timeout=timeout * 1000)
        elif action not in ("snapshot", "switch_tab", "close_tab", "new_tab"):
            raise ValueError("Unsupported browser action")
        result = dict(
            page_id=page_id(page),
            url=page.url,
            title=page.title(),
            text=page.locator("body").inner_text()[:16000],
        )
        result["elements"] = page.locator("a,button,input,textarea,select").evaluate_all("""nodes =>
            nodes.slice(0,80).map((node,index) => {
              node.setAttribute('data-hymio-id', String(index));
              return {selector: '[data-hymio-id="'+index+'"]', tag:node.tagName,
                value:node.type === 'password' ? undefined : (node.value || '').slice(0,200),
                text:(node.innerText || node.getAttribute('aria-label') ||
                  node.placeholder || '').slice(0,160)};
            })""")
        connected.close()
        return result


def computer(args, timeout):
    action = args["action"]
    if action == "screenshot":
        with tempfile.TemporaryDirectory() as directory:
            path = directory + "/screen.png"
            subprocess.run(["scrot", path], check=True, timeout=timeout)
            with open(path, "rb") as file:
                return {"screenshot_base64": base64.b64encode(file.read()).decode()}
    if action == "click":
        x, y = int(args["x"]), int(args["y"])
        if not 0 <= x < 1280 or not 0 <= y < 800:
            raise ValueError("Coordinates outside 1280x800 desktop")
        command = ["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"]
    elif action == "type":
        command = ["xdotool", "type", "--clearmodifiers", "--", args["text"]]
    elif action == "key":
        command = ["xdotool", "key", "--clearmodifiers", args["key"]]
    elif action == "scroll":
        amount = int(args.get("amount", 3))
        if not 1 <= abs(amount) <= 20:
            raise ValueError("Scroll amount must be 1..20")
        command = ["xdotool", "click", "--repeat", str(abs(amount)), "5" if amount > 0 else "4"]
    else:
        raise ValueError("Unsupported computer action")
    subprocess.run(command, check=True, timeout=timeout, capture_output=True)
    return {"performed": action}


def execute(request):
    timeout = max(0.1, min(float(request["timeout"]), 120))
    args = request["arguments"]
    if request["capability"] == "bash":
        return shell(args["command"], args.get("cwd") or os.path.expanduser("~/workspace"), timeout)
    if request["capability"] == "browser":
        return browser(args, timeout)
    if request["capability"] == "computer":
        return computer(args, timeout)
    raise ValueError("Unsupported capability")
