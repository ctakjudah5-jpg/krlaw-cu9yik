# ---------------------------------------------------------------
# Key entry window — save this file AS IS to C:\krlaw\setup_key.py.
#
# Why a window and not the command prompt: people paste keys with
# quotes and stray spaces, and a black console is where they get lost.
# The key box is masked so the key never shows on a lecture-room screen.
#
# The key is checked in TWO steps, because a mistyped key can still pass
# a search (measured). Only the article-body call is a real gate:
#   1) lawSearch.do  target=law   type=XML   (one search)
#   2) lawService.do target=eflaw type=JSON  ID=<법령ID from step 1>
# Use 법령ID, never 법령일련번호(MST): target=eflaw with MST alone is
# refused with a "미신청" notice (measured 2026-08-29), which would make
# a good key look bad.
#
# That notice must NOT be detected by the word alone. Statutes contain
# "미신청" in their own text (form tables in 시행규칙). The real notice is
# a short HTML page (1,455 chars measured), so all three must hold:
# under 8,000 chars, not JSON, and contains "미신청된". See is_refusal().
#
# The key value is never printed — not in the window, not on the console,
# not in any message. Only "확인됨 / 안 됨".
# ---------------------------------------------------------------
import datetime
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FOLDER = r"C:\krlaw"
KEY_FILE = os.path.join(FOLDER, "law_oc.txt")
OWNER_FILE = os.path.join(FOLDER, "owner.txt")
SERVER_FILE = os.path.join(FOLDER, "my_law_server.py")
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}
PROBE_LAW = "소득세법"

STAMP_1 = "# 제작: {name} · AI 세무실무 강의 실습 · {date}"
STAMP_2 = "# 개인 실습용 도구 — 재배포 금지"

MSG_OK = "확인되었습니다"
MSG_BAD = "이 키로는 조회가 되지 않습니다 — 키를 한 글자씩 다시 확인하세요"
MSG_COMBO = "조회 조합 오류입니다 — 키는 그대로 두고 손을 드세요"


def clean_key(s):
    """Drop surrounding spaces and any quote characters people paste in."""
    return (s or "").strip().strip("\"'“”‘’").strip()


def http_get(url, params, timeout=30):
    full = url + "?" + urllib.parse.urlencode(params, encoding="utf-8")
    req = urllib.request.Request(full, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def is_refusal(raw):
    """The '미신청' notice — three signals together, never the word alone."""
    return (len(raw) < 8000
            and not raw.lstrip().startswith(("{", "["))
            and "미신청된" in raw)


def verify_key(oc):
    """Return (ok, message). The message never contains the key."""
    if not oc:
        return False, MSG_BAD
    try:
        # step 1: a search
        raw = http_get("https://www.law.go.kr/DRF/lawSearch.do",
                       {"OC": oc, "target": "law", "type": "XML", "query": PROBE_LAW})
        rows = list(ET.fromstring(raw).iter("law"))
        exact = [r for r in rows if (r.findtext("법령명한글") or "").strip() == PROBE_LAW]
        pick = (exact or rows or [None])[0]
        law_id = (pick.findtext("법령ID") or "").strip() if pick is not None else ""
        if not law_id:
            return False, MSG_BAD
        # step 2: the article body, addressed by 법령ID
        body = http_get("https://www.law.go.kr/DRF/lawService.do",
                        {"OC": oc, "target": "eflaw", "type": "JSON", "ID": law_id})
    except Exception:
        return False, MSG_BAD
    if is_refusal(body):
        return False, MSG_COMBO
    try:
        ok = isinstance(json.loads(body).get("법령"), dict)
    except ValueError:
        ok = False
    return (True, MSG_OK) if ok else (False, MSG_BAD)


def write_text(path, text):
    """UTF-8 without BOM — the server reads these back with plain utf-8."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def stamp_server(name, today=None):
    """Put the two stamp lines at the top of my_law_server.py.
    If a stamp is already there, replace those two lines instead of adding."""
    if not os.path.exists(SERVER_FILE):
        return False
    today = today or datetime.date.today().isoformat()
    with open(SERVER_FILE, encoding="utf-8") as f:
        lines = f.read().split("\n")
    head = [STAMP_1.format(name=name, date=today), STAMP_2]
    rest = lines
    if len(lines) >= 2 and lines[0].startswith("# 제작:") and lines[1].startswith("# 개인 실습용 도구"):
        rest = lines[2:]
    write_text(SERVER_FILE, "\n".join(head + rest))
    return True


def save_all(oc, name):
    os.makedirs(FOLDER, exist_ok=True)
    write_text(KEY_FILE, oc)
    write_text(OWNER_FILE, name)
    return stamp_server(name)


def main():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("법제처 인증키")
    root.resizable(False, False)
    pad = {"padx": 12, "pady": 6}

    tk.Label(root, text="본인 이름 (만든 사람 표시로 파일에 남습니다)").grid(row=0, column=0, sticky="w", **pad)
    name_box = tk.Entry(root, width=36)
    name_box.grid(row=1, column=0, **pad)

    tk.Label(root, text="발급받은 OC 를 붙여넣으세요 (따옴표 없이)").grid(row=2, column=0, sticky="w", **pad)
    key_box = tk.Entry(root, width=36, show="*")          # masked on purpose
    key_box.grid(row=3, column=0, **pad)

    status = tk.Label(root, text="", fg="#555555")
    status.grid(row=5, column=0, **pad)

    def on_ok():
        name = (name_box.get() or "").strip()
        oc = clean_key(key_box.get())
        if not name or not oc:
            messagebox.showwarning("법제처 인증키", "이름과 인증키를 모두 넣어 주세요.")
            return
        button.config(state="disabled")
        status.config(text="확인 중… (몇 초 걸립니다)")
        root.update()
        ok, msg = verify_key(oc)
        if ok:
            stamped = save_all(oc, name)
            note = "" if stamped else "\n(my_law_server.py 가 아직 없어 이름 도장은 건너뛰었습니다)"
            messagebox.showinfo("법제처 인증키", msg + note)
            root.destroy()
        else:
            messagebox.showerror("법제처 인증키", msg)
            status.config(text="")
            button.config(state="normal")

    button = tk.Button(root, text="확인", width=12, command=on_ok)
    button.grid(row=4, column=0, **pad)
    name_box.focus_set()
    root.mainloop()


if __name__ == "__main__":
    main()
