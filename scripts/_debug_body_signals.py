import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "backend")

from storage.sqlite_db import get_conn

ids_to_check = [309, 294, 292, 291, 290, 287, 284, 282, 279, 278, 275, 274, 271,
                261, 258, 255, 253, 252, 247, 246, 243, 241, 240, 238, 245]

RE_UNSUB = re.compile(r"(?i)unsubscribe")
RE_HTML_TABLE = re.compile(r"(?i)<table|<style|cellpadding|<!doctype\s+html")
RE_PERCENT_OFF = re.compile(r"(?i)\d+\s*%\s*off")
RE_SHOP_NOW = re.compile(r"(?i)\b(shop|buy|order|sale|claim|download)\s+(now|here|today)\b")
RE_VIEW_BROWSER = re.compile(r"(?i)view\s+(this\s+email\s+)?(online|in\s+your\s+browser)")

with get_conn() as c:
    rows = c.execute(
        f"SELECT id, text, payload_json FROM messages WHERE id IN ({','.join('?'*len(ids_to_check))})",
        ids_to_check,
    ).fetchall()

for r in rows:
    text = str(r["text"] or "")
    try:
        p = json.loads(r["payload_json"] or "{}")
    except Exception:
        p = {}
    payload_text = str(p.get("text") or p.get("body") or "")
    snippet = str(p.get("snippet") or "")

    best = text if len(text) >= len(payload_text) else payload_text
    hit_unsub = bool(RE_UNSUB.search(best))
    hit_html = bool(RE_HTML_TABLE.search(best))
    hit_off = bool(RE_PERCENT_OFF.search(best))
    hit_shop = bool(RE_SHOP_NOW.search(best))
    hit_view = bool(RE_VIEW_BROWSER.search(best))

    print(
        f"id={r['id']:>4} "
        f"len_text={len(text):>5} len_pl={len(payload_text):>5} len_snip={len(snippet):>3} "
        f"unsub={int(hit_unsub)} html={int(hit_html)} off={int(hit_off)} "
        f"shop={int(hit_shop)} view={int(hit_view)} "
        f"sender={str(p.get('from') or p.get('sender') or '')[:50]}"
    )
