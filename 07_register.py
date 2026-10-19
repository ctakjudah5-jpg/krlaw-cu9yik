# ---------------------------------------------------------------
# Register your MCP server with the Claude desktop app.
#
# Run this ONLY while the Claude app is fully closed. Two reasons:
#   1) A running app rewrites its own config on exit, silently undoing
#      any edit made underneath it — the single most common failure.
#   2) Claude Code lives inside the app, so it cannot make this edit
#      for you. You double-click; no command prompt needed.
#
# It also handles the Microsoft Store build, whose config lives in an
# isolated per-package folder rather than %APPDATA%. Both locations are
# written, so it works either way.
# ---------------------------------------------------------------
import datetime
import glob
import json
import os
import subprocess
import sys

SERVER_NAME = "law-axtax"
SERVER_PY = r"C:\krlaw\my_law_server.py"


def show(title, body, error=True):
    """Report through a window — this program is launched by double-click."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        (messagebox.showerror if error else messagebox.showinfo)(title, body)
        root.destroy()
    except Exception:
        print(title, "\n", body)


def claude_running():
    """True while any Claude process is alive (app or Claude Code)."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Claude.exe", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        return "claude.exe" in (out or "").lower()
    except Exception:
        return False


def config_paths():
    """Every config location that could apply on this PC.
    Newer Store builds (2.4x~, 2026-10) read %LOCALAPPDATA%\\Claude-Data\\claude_*;
    older Store builds keep theirs under LocalCache\\Packages; the plain
    installer uses %APPDATA%. Write all — the unused ones are harmless."""
    found = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        # 2026-10-18: a fresh Store install (2.42304) read ONLY this location, so the
        # old script reported success while the app never saw the entry.
        for data_dir in glob.glob(os.path.join(local, "Claude-Data", "claude_*")):
            found.append((os.path.join(data_dir, "claude_desktop_config.json"),
                          "Store 버전 (새 위치)"))
        for pkg in glob.glob(os.path.join(local, "Packages", "Claude_*")):
            found.append((os.path.join(pkg, "LocalCache", "Roaming", "Claude",
                                       "claude_desktop_config.json"), "Store 버전"))
    roaming = os.environ.get("APPDATA", "")
    if roaming:
        found.append((os.path.join(roaming, "Claude",
                                   "claude_desktop_config.json"), "일반 설치본"))
    return found


def register_one(path):
    """Merge our entry into one config file. Returns a report line."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        raw = open(path, "rb").read()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        open("%s.backup_%s" % (path, stamp), "wb").write(raw)   # back up first
        body = raw.decode("utf-8-sig", "replace").strip()
        if body:
            try:
                data = json.loads(body)
            except ValueError:
                return "실패 — 기존 설정 파일이 깨져 있습니다:\n   %s" % path
    if not isinstance(data, dict):
        data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    before = sorted(servers.keys())
    # Replace only our own entry by exact name; every other server stays.
    servers[SERVER_NAME] = {"command": sys.executable or "python",
                            "args": [SERVER_PY]}
    data["mcpServers"] = servers
    open(path, "wb").write(json.dumps(data, ensure_ascii=False,
                                      indent=2).encode("utf-8"))   # no BOM

    check = json.loads(open(path, "rb").read().decode("utf-8-sig", "replace"))
    if check.get("mcpServers", {}).get(SERVER_NAME, {}).get("args") != [SERVER_PY]:
        return "실패 — 저장한 뒤 확인했는데 항목이 없습니다:\n   %s" % path
    kept = [k for k in before if k in check["mcpServers"] and k != SERVER_NAME]
    return "성공 — %s\n   함께 유지된 기존 항목 %d개%s" % (
        path, len(kept), (": " + ", ".join(kept)) if kept else "")


def main():
    if claude_running():
        show("Claude 앱이 아직 켜져 있습니다",
             "작업 관리자(Ctrl+Shift+Esc)에서 Claude 를 모두 끝내기 한 뒤\n"
             "이 프로그램을 다시 실행해 주세요.\n\n"
             "앱이 켜진 채로 설정을 고치면, 앱이 자기 설정을 다시 쓰면서\n"
             "방금 넣은 항목을 지워 버립니다.")
        return 1
    if not os.path.exists(SERVER_PY):
        show("서버 파일을 찾지 못했습니다",
             "%s 가 없습니다.\n앞 단계에서 만든 파일 이름과 위치를 확인해 주세요." % SERVER_PY)
        return 1
    lines = [("[%s]\n%s" % (kind, register_one(path)))
             for path, kind in config_paths()]
    if not lines:
        show("설정 위치를 찾지 못했습니다", "Claude 데스크톱 앱이 설치되어 있는지 확인해 주세요.")
        return 1
    body = "\n\n".join(lines)
    ok = all("성공" in ln for ln in lines)
    if ok:
        show("등록되었습니다", "이제 Claude 앱을 다시 켜세요.\n\n" + body, error=False)
    else:
        show("일부 실패했습니다", body)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
