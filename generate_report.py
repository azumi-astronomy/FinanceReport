#!/usr/bin/env python3
"""
Daily Finance Research Report Generator
Claude API (claude-sonnet-4-6) + Web Search → HTML → GitHub Pages
Schedule: 08:00 JST daily via GitHub Actions
"""

import anthropic
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 日時設定 ─────────────────────────────────────────────
JST = timezone(timedelta(hours=9))
today     = datetime.now(JST)
DATE_STR  = today.strftime('%Y%m%d')           # 例: 20260527
TIME_STR  = today.strftime('%H%M')             # 例: 0800
DATE_JA   = today.strftime('%Y年%m月%d日')
WEEKDAY   = '月火水木金土日'[today.weekday()]

PREV_DATE = (today - timedelta(days=1)).strftime('%Y%m%d')
NEXT_DATE = (today + timedelta(days=1)).strftime('%Y%m%d')

TODAY_FILE = f'research_report_{DATE_STR}_{TIME_STR}.html'

# 前日レポートは時刻不明なのでglobで検索
_prev_candidates = sorted(Path(__file__).parent.glob(f'research_report_{PREV_DATE}_????.html'))
PREV_FILE = _prev_candidates[-1].name if _prev_candidates else f'research_report_{PREV_DATE}_0000.html'

BASE_DIR = Path(__file__).parent


# ── HTML 生成 ──────────────────────────────────────────────
def generate_html() -> str:
    client = anthropic.Anthropic()   # ANTHROPIC_API_KEY を環境変数から自動取得

    prev_exists = (BASE_DIR / PREV_FILE).exists()
    prev_nav = (
        f'href="{PREV_FILE}"'
        if prev_exists
        else 'href="#" style="opacity:0.35;pointer-events:none;"'
    )

    prompt = (BASE_DIR / 'prompt.txt').read_text(encoding='utf-8')
    prompt = (prompt
              .replace('__DATE_JA__', DATE_JA)
              .replace('__WEEKDAY__', WEEKDAY)
              .replace('__PREV_NAV__', prev_nav))

    print(f"[API] Calling claude-sonnet-4-6 with web_search (max 15 uses)...")
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=24000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 15,
        }],
        system=(
            "あなたは世界最高水準の株式リサーチアナリストです。"
            "要求されたHTMLファイルの内容だけを出力してください。"
            "余計なテキスト・コードブロック・説明は一切含めないでください。"
        ),
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    # テキストブロックのみ結合（tool_use / tool_result ブロックは除外）
    html = "".join(b.text for b in response.content if b.type == "text")

    # 誤ってコードフェンスが混入した場合はクリーンアップ
    html = re.sub(r'^```(?:html)?\s*\n?', '', html.strip(), flags=re.IGNORECASE)
    html = re.sub(r'\n?```\s*$', '', html, flags=re.IGNORECASE)

    # <!DOCTYPE から始まるように補正
    idx = html.lower().find('<!doctype')
    if idx > 0:
        html = html[idx:]

    print(f"[API] Done — {len(html):,} chars, stop_reason={response.stop_reason}")
    return html


# ── 生成レポートの数値検証・修正 ────────────────────────────────
def verify_and_fix_report(html: str) -> str:
    """レポートの価格データをWeb検索で検証し、誤りを修正して返す"""
    import json as json_lib

    client = anthropic.Anthropic()

    # HTMLからテキスト抽出（タグ除去）
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()[:6000]

    print("[CHK] Verifying financial data with web search (max 10)...")
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        system=(
            "あなたは金融データ検証エージェントです。"
            "指示に従い、JSONのみを出力してください。説明文・コードブロックは不要です。"
        ),
        messages=[{"role": "user", "content": f"""
以下のレポートテキスト（{DATE_JA}付）から株価・指数・暗号資産・貴金属の価格を読み取り、
Web検索で正確な値を確認してください。

【手順】
1. レポートから価格データを抽出する
2. 各データをWeb検索で確認する
3. 誤りがある項目のみ以下のJSON形式で返す（正しい場合は含めない）

【出力形式】JSONのみ・前後の説明不要
[
  {{
    "銘柄": "銘柄名または指標名",
    "レポート値": "レポートに記載の値（HTMLで検索できる正確な文字列）",
    "正確な値": "Web検索で確認した正しい値（同じ形式・単位で）"
  }}
]

誤りがない場合: []

レポートテキスト:
{text}
"""}]
    ) as stream:
        response = stream.get_final_message()

    result_text = "".join(b.text for b in response.content if b.type == "text").strip()
    print(f"[CHK] Raw result: {result_text[:500]}")

    json_match = re.search(r'\[[\s\S]*\]', result_text)
    if not json_match:
        print("[CHK] Could not parse JSON. Skipping corrections.")
        return html

    try:
        corrections = json_lib.loads(json_match.group())
    except json_lib.JSONDecodeError:
        print("[CHK] JSON parse error. Skipping corrections.")
        return html

    if not corrections:
        print("[CHK] All data verified. No corrections needed.")
        return html

    fixed_html = html
    applied = 0
    for c in corrections:
        wrong = c.get('レポート値', '')
        correct = c.get('正確な値', '')
        name = c.get('銘柄', '?')
        if not wrong or not correct or wrong == correct:
            continue
        fixed_html, ok = _flexible_replace(fixed_html, wrong, correct, name)
        if ok:
            applied += 1

    print(f"[CHK] Applied {applied}/{len(corrections)} correction(s)")
    return fixed_html


def _flexible_replace(html: str, wrong: str, correct: str, label: str) -> tuple:
    """フォーマット差異を吸収しながら数値を置換する"""

    # 戦略1: 完全一致
    if wrong in html:
        print(f"[CHK] Fixed [{label}]: {wrong} → {correct}")
        return html.replace(wrong, correct, 1), True

    # 数字部分だけを抽出（カンマ・通貨記号・単位を除去）
    digits = re.sub(r'[^\d.]', '', wrong)
    if not digits:
        print(f"[CHK] Skip [{label}]: no numeric value in '{wrong}'")
        return html, False

    try:
        n = int(float(digits))
    except ValueError:
        print(f"[CHK] Skip [{label}]: cannot parse number from '{wrong}'")
        return html, False

    # 戦略2: 数値の表記揺れパターンを順に試す
    candidates = [
        f'{n:,}円',   # 4,280円
        f'¥{n:,}',    # ¥4,280
        f'￥{n:,}',   # ￥4,280
        f'{n}円',     # 4280円
        f'¥{n}',      # ¥4280
        f'{n:,}',     # 4,280
        str(n),       # 4280
    ]
    for candidate in candidates:
        if candidate in html:
            print(f"[CHK] Fixed [{label}] (fuzzy '{candidate}'): → {correct}")
            return html.replace(candidate, correct, 1), True

    # 戦略3: 正規表現で柔軟にマッチ（カンマ有無・通貨記号有無）
    num_str = str(n)
    # 3桁区切りのカンマをオプショナルに
    flexible = re.sub(r'(\d)(?=(\d{3})+$)', r'\1,?', num_str)
    pattern = rf'[¥￥$]?\s*{flexible}\s*[円ドル]?'
    m = re.search(pattern, html)
    if m:
        matched = m.group()
        print(f"[CHK] Fixed [{label}] (regex '{matched}'): → {correct}")
        return html[:m.start()] + correct + html[m.end():], True

    print(f"[CHK] Skip [{label}]: '{wrong}' not found in HTML (tried {len(candidates)} patterns + regex)")
    return html, False


# ── 前日レポートに「翌日 →」リンクを追加 ───────────────────────
def activate_next_link_in_prev():
    prev_path = BASE_DIR / PREV_FILE
    if not prev_path.exists():
        return

    content = prev_path.read_text(encoding='utf-8')
    if 'data-placeholder="true"' not in content:
        return  # すでに更新済みまたはパターンなし

    updated = content.replace(
        'data-placeholder="true" style="opacity:0.35;pointer-events:none;"',
        f'href="{TODAY_FILE}"',
    )
    if updated != content:
        prev_path.write_text(updated, encoding='utf-8')
        print(f"[NAV] Activated next-day link in {PREV_FILE}")


# ── index.html を再生成 ──────────────────────────────────────
def rebuild_index():
    reports = []
    # 新フォーマット（YYYYMMDD_HHMM）と旧フォーマット（YYYYMMDD）の両方を収集
    all_files = sorted(
        list(BASE_DIR.glob('research_report_????????_????.html')) +
        list(BASE_DIR.glob('research_report_????????.html')),
        reverse=True
    )
    for f in all_files:
        stem = f.stem.replace('research_report_', '')
        try:
            if '_' in stem:
                d_str, t_str = stem.split('_')
            else:
                d_str, t_str = stem, ''
            d = datetime.strptime(d_str, '%Y%m%d').replace(tzinfo=JST)
            reports.append({
                'date_str': d_str,
                'time_str': t_str,
                'display':  d.strftime('%Y年%m月%d日'),
                'weekday':  '月火水木金土日'[d.weekday()],
                'file':     f.name,
                'is_new':   f.name == TODAY_FILE,
            })
        except ValueError:
            pass

    rows = ""
    for r in reports:
        badge = '<span class="badge-new">NEW</span>' if r['is_new'] else ''
        time_label = f'{r["time_str"][:2]}:{r["time_str"][2:]}'
        rows += (
            f'\n      <tr data-date="{r["date_str"]}">'
            f'<td><a href="{r["file"]}">{r["display"]}（{r["weekday"]}）{badge}</a>'
            f'<span style="color:#6b7a99;font-size:11px;margin-left:8px;">{time_label}</span></td>'
            f'<td><a href="{r["file"]}" class="btn-open">開く →</a></td></tr>'
        )

    latest = reports[0]['display'] if reports else '—'
    oldest = reports[-1]['display'] if reports else '—'
    count  = len(reports)

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Finance Research Reports</title>
<style>
:root{{--bg:#0b0e14;--sf:#111827;--s2:#1a2235;--bd:#263352;--tx:#e8edf5;--mu:#6b7a99;--bl:#3b82f6;--or:#f97316;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--tx);font-family:'Segoe UI',system-ui,sans-serif;
      padding:28px 20px 60px;max-width:860px;margin:0 auto;}}
.hdr{{background:linear-gradient(135deg,#0c1a3e,#111827);border:1px solid var(--bd);
      border-radius:12px;padding:26px 28px;margin-bottom:22px;}}
.hdr h1{{font-size:21px;font-weight:800;color:#fff;margin-bottom:5px;}}
.hdr p{{color:var(--mu);font-size:11px;line-height:1.6;}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;}}
.stat{{background:var(--sf);border:1px solid var(--bd);border-radius:8px;padding:14px;}}
.stat .n{{font-size:22px;font-weight:800;color:var(--bl);margin-bottom:3px;}}
.stat .l{{font-size:10px;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;}}
table{{width:100%;border-collapse:collapse;background:var(--sf);border:1px solid var(--bd);border-radius:10px;overflow:hidden;}}
th{{background:var(--s2);color:var(--mu);font-size:10px;text-transform:uppercase;
    letter-spacing:.1em;padding:10px 14px;text-align:left;border-bottom:1px solid var(--bd);}}
td{{padding:12px 14px;border-bottom:1px solid var(--bd);font-size:13px;}}
tr:last-child td{{border-bottom:none;}}
tr:hover td{{background:var(--s2);}}
td a{{color:var(--bl);text-decoration:none;}}
td a:hover{{text-decoration:underline;}}
.btn-open{{background:var(--bl);color:#fff!important;padding:5px 14px;border-radius:6px;
           font-size:11px;font-weight:700;display:inline-block;}}
.btn-open:hover{{opacity:.85;text-decoration:none!important;}}
.badge-new{{background:#2d1100;color:var(--or);border:1px solid var(--or);border-radius:10px;
            font-size:9px;font-weight:700;padding:1px 7px;margin-left:6px;vertical-align:middle;}}
.foot{{margin-top:18px;color:var(--mu);font-size:10px;text-align:center;}}
@media(max-width:540px){{.stats{{grid-template-columns:1fr 1fr;}}body{{padding:16px 12px 40px;}}}}
</style>
</head>
<body>
<div class="hdr">
  <h1>📊 Finance Research Reports</h1>
  <p>
    グローバル市場 日次株式リサーチレポート｜毎日 8:00 JST 自動生成<br/>
    株式（日本・米国）｜貴金属｜暗号資産｜日本株10選・米国株10選
  </p>
</div>
<div class="stats">
  <div class="stat"><div class="n">{count}</div><div class="l">総レポート数</div></div>
  <div class="stat"><div class="n" style="font-size:13px;">{latest}</div><div class="l">最新レポート</div></div>
  <div class="stat"><div class="n" style="font-size:13px;">{oldest}</div><div class="l">最初のレポート</div></div>
</div>
<table>
  <thead><tr><th>日付</th><th>アクション</th></tr></thead>
  <tbody>{rows}
  </tbody>
</table>
<div class="foot">
  自動生成 by Claude Sonnet 4.6（Anthropic）｜本レポートは投資推奨ではありません。投資は自己責任でお願いします。
</div>
</body>
</html>'''

    (BASE_DIR / 'index.html').write_text(html, encoding='utf-8')
    print(f"[IDX] index.html rebuilt — {count} report(s) listed")


# ── エントリポイント ─────────────────────────────────────────
def main():
    print(f"=== Finance Report Generator | {DATE_JA}（{WEEKDAY}） ===")

    report_path = BASE_DIR / TODAY_FILE

    # 1. レポート HTML 生成
    html = generate_html()
    if len(html) < 2000:
        raise RuntimeError(f"Generated HTML too short ({len(html)} chars) — aborting.")

    # 2. 数値検証・修正
    html = verify_and_fix_report(html)

    # 3. 保存
    report_path.write_text(html, encoding='utf-8')
    print(f"[OUT] Saved: {TODAY_FILE} ({len(html):,} chars)")

    # 4. 前日レポートの「翌日 →」リンクを有効化
    activate_next_link_in_prev()

    # 5. index.html 再生成
    rebuild_index()

    print("=== Complete ===")


if __name__ == '__main__':
    main()
