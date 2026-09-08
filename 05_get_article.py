# ---------------------------------------------------------------
# Article text — an article is addressed by a 6-digit code:
# 4 digits for the article number + 2 for its branch ("의N").
#     제38조    -> 0038 + 00 = "003800"
#     제10조의2 -> 0010 + 02 = "001002"
# The statute itself is addressed by 법령ID, taken from search (04).
#
# This file also guards against four quirks of the API that are
# documented nowhere — two in how the request is sent, two in
# how the response is read.
# ---------------------------------------------------------------
import json
import os
import re
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}


def read_key():
    """Never hard-code the key. Read the env var first, then the local file."""
    oc = (os.environ.get("LAW_OC") or "").strip()
    if oc:
        return oc
    try:
        with open(r"C:\krlaw\law_oc.txt", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def http_get(url, params):
    full = url + "?" + urllib.parse.urlencode(params, encoding="utf-8")
    req = urllib.request.Request(full, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def jo_code(jo):
    """'제38조' / '제10조의2' / '38' -> 6-digit code."""
    jo = str(jo).strip()
    if re.fullmatch(r"\d{6}", jo):
        return jo
    m = re.search(r"제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?", jo)
    if m:
        return "%04d%02d" % (int(m.group(1)), int(m.group(2) or 0))
    return "%04d00" % int(jo) if jo.isdigit() else jo


def text_of(v):
    """Quirk (response side): 조문내용/항내용/호내용 are not always strings.
    Deeply nested articles return them as lists (sometimes dicts).
    Treat them as strings and you crash — or silently lose text.
    Recover the text from any shape, in document order."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n".join(t for t in (text_of(x) for x in v) if t)
    if isinstance(v, dict):
        return "\n".join(t for t in (text_of(x) for x in v.values()) if t)
    return str(v)


def as_list(x):
    """The API returns one item as a dict, several as a list — normalize."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _num(x):
    m = re.search(r"\d+", str(x or ""))
    return int(m.group()) if m else 0


def get_article(law_id, jo):
    """법령ID + article number -> the article's text.

    Quirk (request side #1): passing the article number (JO) as an API
    parameter can silently drop tables attached to the article.
    So fetch the whole statute and pick the article out locally.

    Quirk (request side #2): address the statute by 법령ID — never by
    법령일련번호(MST). Measured 2026-08-29: target=eflaw with MST alone is
    refused. It answers HTTP 200, so nothing looks broken, but the body is
    a notice reading "국가법령정보 공동활용 미신청된 목록/본문에 대한
    접근입니다". The wording blames your API application; your key is fine.
    With the same key, eflaw+ID / law+MST / law+ID / eflaw+MST+efYd all
    return the statute in full.
    Do NOT "fix" this by switching to target=law. That serves the 공포본:
    for 소득세법 it was six months behind the 시행본 (20260101 vs 20260701),
    24 articles differed in body text, and 제164조의4 existed only there."""
    # Callers hand this over from search output ("소득세법 [법령ID 001565] ...").
    # Keep only the digits, so a stray bracket or the label itself is harmless.
    law_id = re.sub(r"\D", "", str(law_id)) or str(law_id)
    raw = http_get("https://www.law.go.kr/DRF/lawService.do", {
        "OC": read_key(), "target": "eflaw", "type": "JSON", "ID": law_id,
    })
    # Check the refusal BEFORE parsing: that notice is HTML, so json.loads
    # would raise first and the useful message would never be reached.
    #
    # Do NOT test the word alone. Statutes contain "미신청" in their own text —
    # the form tables in 시행규칙 별지 서식 carry a cell reading "│신청│미신청│".
    # Measured 2026-09-08: a 3.3MB normal response (법인세법 시행규칙, 137 articles)
    # was rejected wholesale. The real notice is a 1,455-character HTML page, so
    # demand all three signals before calling it a refusal.
    if (len(raw) < 8000
            and not raw.lstrip().startswith(("{", "["))
            and "미신청된" in raw):
        return ("[조회 실패] 법령ID %s — 조회 조합이 잘못됐습니다. "
                "인증키 문제가 아니니 키를 다시 입력하지 마세요." % law_id)
    try:
        data = json.loads(raw)
    except ValueError:
        return "[조회 실패] 법령ID %s — 응답이 JSON 이 아닙니다." % law_id
    law = data.get("법령")
    if not isinstance(law, dict):
        return "[조회 실패] 법령ID %s — 법령 전체본을 받지 못했습니다." % law_id

    jo_node = law.get("조문")
    units = as_list(jo_node.get("조문단위")) if isinstance(jo_node, dict) else as_list(jo_node)
    code = jo_code(jo)
    want_jo, want_ji = int(code[:4]), int(code[4:])
    sel = [u for u in units if isinstance(u, dict)
           and _num(u.get("조문번호")) == want_jo
           and _num(u.get("조문가지번호")) == want_ji]
    if not sel:
        return ("[조문 없음] %s — 이 법령(법령ID %s)에 해당 조문이 없습니다. "
                "폐지되었거나 조문번호가 틀렸을 수 있습니다." % (jo, law_id))

    out = []
    for u in sel:                          # 조 -> 항 -> 호 -> 목, with indentation
        body = text_of(u.get("조문내용"))
        if body:
            out.append(body)
        for hang in as_list(u.get("항")):
            if not isinstance(hang, dict):
                continue
            t = text_of(hang.get("항내용"))
            if t:
                out.append("  " + t.replace("\n", "\n  "))
            for ho in as_list(hang.get("호")):
                if not isinstance(ho, dict):
                    continue
                t2 = text_of(ho.get("호내용"))
                if t2:
                    out.append("    " + t2.replace("\n", "\n    "))
                for mok in as_list(ho.get("목")):
                    if not isinstance(mok, dict):
                        continue
                    t3 = text_of(mok.get("목내용"))
                    if t3:
                        out.append("      " + t3.replace("\n", "\n      "))
            # Quirk (response side #2): in some statutes 목 hangs directly
            # off 항 as a sibling of 호 — not under any 호. Measured live:
            # 소득세법 제12조 has 45 such 목 and zero under its 호.
            # Skip this and all of them vanish silently. The API gives no
            # clue which 호 each one belongs to, so emit them after the
            # 호 list — imperfect ordering beats losing the text.
            for mok in as_list(hang.get("목")):
                if not isinstance(mok, dict):
                    continue
                t3 = text_of(mok.get("목내용"))
                if t3:
                    out.append("      " + t3.replace("\n", "\n      "))
    return "\n".join(out)


if __name__ == "__main__":
    # Check the numbering rule (works without a key).
    print(jo_code("제38조"), jo_code("제10조의2"))   # 003800 001002
    # The full-text demo needs a 법령ID — get one via search_law in 04.
