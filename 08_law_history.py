# ---------------------------------------------------------------
# Past versions of a statute — history list, article at a date, addenda.
#
# A version of a statute is the PAIR (MST, 시행일자). Never one of them alone.
#   · One MST can carry several 시행일자 (staged enforcement). Measured
#     2026-09-11: 소득세법 MST 280405 has both a 2026-07-01 and a
#     2027-01-01 version. So pick a ROW from the history list and use
#     that row's MST and 시행일자 together.
#   · efYd must equal the row's 시행일자 exactly. "Around that date" is
#     refused. To find the law in force on some date, take the row with
#     the latest 시행일자 on or before it (that is the 행위시법).
#
# Only one request shape returns the right version (measured on three
# historical 소득세법 rows, 2026-09-11):
#     target=eflaw + MST + efYd   -> exact version          <- use this
#     target=eflaw + MST          -> refused ("미신청" notice)
#     target=eflaw + ID  + efYd   -> empty {}
#     target=law   + MST          -> answers, but can be a DIFFERENT version:
#                                    asked for the 2019-01-01 version,
#                                    got the 2015-01-01 one. No error shown.
# Do not fall back to target=law. A wrong year with no error is worse
# than a clear failure.
#
# Addenda (부칙: 적용례·경과조치) come in the SAME response as the
# articles, under 부칙 > 부칙단위, keyed by 부칙공포번호. Comparing article
# text alone gives wrong summaries: most errors in a real 2025 vs 2026
# comparison came from missing the addenda, not from the article text.
# ---------------------------------------------------------------
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/"}
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
DETAIL_URL = "https://www.law.go.kr/DRF/lawService.do"


def read_key():
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def digits(x):
    """Keep only digits: '제21223호' -> '21223', '2019.01.01' -> '20190101'."""
    return re.sub(r"\D", "", str(x or ""))


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def text_of(v):
    """Text fields arrive as str, list or dict depending on depth."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n".join(t for t in (text_of(x) for x in v) if t)
    if isinstance(v, dict):
        return "\n".join(t for t in (text_of(x) for x in v.values()) if t)
    return str(v)


# -- 1. history list -----------------------------------------------
def history_rows(name):
    """All versions of the statute named exactly `name`, newest first."""
    raw = http_get(SEARCH_URL, {"OC": read_key(), "target": "eflaw", "type": "XML",
                                "query": name, "display": "100"})
    rows = []
    for r in ET.fromstring(raw).iter("law"):
        if (r.findtext("법령명한글") or "").strip() != name:
            continue                    # search is loose; keep exact names only
        rows.append({
            "mst": (r.findtext("법령일련번호") or "").strip(),
            "efyd": digits(r.findtext("시행일자")),
            "prom_date": digits(r.findtext("공포일자")),
            "prom_no": (r.findtext("공포번호") or "").strip(),
            "kind": (r.findtext("제개정구분명") or "").strip(),
            "state": (r.findtext("현행연혁코드") or "").strip(),   # 현행 / 연혁 / 시행예정
        })
    # Several acts can take effect on the same day (staged enforcement):
    # 소득세법 has three rows with 시행일 20190101, promulgated in 2014, 2017
    # and 2018 — each a different consolidated text. The one in force that
    # day is the latest promulgated, so break ties on 공포일자.
    rows.sort(key=lambda x: (x["efyd"], x["prom_date"]), reverse=True)
    return rows


def list_law_history(name):
    rows = history_rows(name)
    if not rows:
        return "[연혁 없음] '%s' 와 이름이 정확히 같은 법령을 찾지 못했습니다." % name
    lines = ["%s — 시행일 기준 %d개 판 (최신순)" % (name, len(rows)),
             "※ 판은 (MST, 시행일자) 짝으로 고릅니다. 조회할 때 두 값을 함께 넘기세요."]
    for x in rows[:30]:
        lines.append("  시행 %s · 공포 %s 제%s호 · %s · %s · MST %s"
                     % (x["efyd"], x["prom_date"], x["prom_no"], x["kind"], x["state"], x["mst"]))
    if len(rows) > 30:
        lines.append("  … 외 %d개 판" % (len(rows) - 30))
    return "\n".join(lines)


def version_at(name, date):
    """The (MST, 시행일자) pair in force on `date` — the latest efyd <= date."""
    d = digits(date)
    cands = [x for x in history_rows(name) if x["efyd"] and x["efyd"] <= d]
    return cands[0] if cands else None


# -- 2. one version, fetched once --------------------------------------
def fetch_version(mst, efyd):
    """The whole statute as it read at (mst, efyd). Returns (law, error)."""
    mst, efyd = digits(mst), digits(efyd)
    if not mst or len(efyd) != 8:
        return None, "[조회 실패] MST 와 시행일자(8자리)를 함께 넘기세요. 하나만으로는 판이 정해지지 않습니다."
    raw = http_get(DETAIL_URL, {"OC": read_key(), "target": "eflaw", "type": "JSON",
                                "MST": mst, "efYd": efyd})
    if len(raw) < 8000 and not raw.lstrip().startswith(("{", "[")) and "미신청된" in raw:
        return None, ("[조회 실패] MST %s · 시행일 %s — 조회 조합이 잘못됐습니다. "
                      "인증키 문제가 아니니 키를 다시 입력하지 마세요." % (mst, efyd))
    try:
        law = json.loads(raw).get("법령")
    except ValueError:
        law = None
    if not isinstance(law, dict):
        return None, ("[조회 실패] MST %s · 시행일 %s — 그 짝의 판이 없습니다. 시행일자는 연혁 목록의 "
                      "그 행 값을 그대로 넣어야 합니다('그 무렵 날짜'는 거부됩니다)." % (mst, efyd))
    got = digits((law.get("기본정보") or {}).get("시행일자"))
    if got != efyd:                    # never hand back a different version silently
        return None, "[조회 실패] 요청한 시행일 %s 가 아니라 %s 판이 왔습니다. 쓰지 마세요." % (efyd, got)
    return law, None


def jo_code(jo):
    jo = str(jo).strip()
    if re.fullmatch(r"\d{6}", jo):
        return jo
    m = re.search(r"제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?", jo)
    if m:
        return "%04d%02d" % (int(m.group(1)), int(m.group(2) or 0))
    return "%04d00" % int(jo) if jo.isdigit() else jo


def _num(x):
    m = re.search(r"\d+", str(x or ""))
    return int(m.group()) if m else 0


def get_article_at(mst, efyd, jo):
    law, err = fetch_version(mst, efyd)
    if err:
        return err
    code = jo_code(jo)
    want_jo, want_ji = int(code[:4]), int(code[4:])
    node = law.get("조문")
    units = as_list(node.get("조문단위")) if isinstance(node, dict) else as_list(node)
    sel = [u for u in units if isinstance(u, dict) and u.get("조문여부") != "전문"
           and _num(u.get("조문번호")) == want_jo and _num(u.get("조문가지번호")) == want_ji]
    if not sel:
        return "[조문 없음] %s — 시행일 %s 판에는 이 조문이 없습니다." % (jo, digits(efyd))
    out = ["=== %s [시행 %s] ===" % ((law.get("기본정보") or {}).get("법령명_한글", ""), digits(efyd))]
    for u in sel:
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
                    if isinstance(mok, dict) and text_of(mok.get("목내용")):
                        out.append("      " + text_of(mok.get("목내용")).replace("\n", "\n      "))
            for mok in as_list(hang.get("목")):       # 목 can hang straight off 항 (see 05)
                if isinstance(mok, dict) and text_of(mok.get("목내용")):
                    out.append("      " + text_of(mok.get("목내용")).replace("\n", "\n      "))
    return "\n".join(out)


# -- 3. addenda ----------------------------------------------------------
def get_addenda(mst, efyd, prom_no):
    """The addenda of one amending act (by 공포번호), as carried in that version."""
    law, err = fetch_version(mst, efyd)
    if err:
        return err
    want = digits(prom_no)
    units = as_list((law.get("부칙") or {}).get("부칙단위"))
    hit = [u for u in units if isinstance(u, dict)
           and digits(u.get("부칙공포번호")).lstrip("0") == want.lstrip("0")]
    if not hit:
        return "[부칙 없음] 시행일 %s 판에 제%s호 부칙이 없습니다." % (digits(efyd), want)
    out = []
    for u in hit:
        out.append("부칙 <제%s호, %s>" % (digits(u.get("부칙공포번호")), digits(u.get("부칙공포일자"))))
        out.append(text_of(u.get("부칙내용")))
    return "\n".join(out)


if __name__ == "__main__":
    # Hands-on demo (needs a key): 통합고용세액공제, 2025 version vs 2026 version.
    print(list_law_history("조세특례제한법")[:600])
    print()
    print(get_article_at("269877", "20250314", "제29조의8")[:400])
    print()
    print(get_article_at("280409", "20260101", "제29조의8")[:400])
    print()
    a = get_addenda("280409", "20260101", "21223")
    i = a.find("제34조")
    print(a[i:i + 300] if i >= 0 else a[:300])
