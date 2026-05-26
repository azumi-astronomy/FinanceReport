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
DATE_JA   = today.strftime('%Y年%m月%d日')
WEEKDAY   = '月火水木金土日'[today.weekday()]

PREV_DATE = (today - timedelta(days=1)).strftime('%Y%m%d')
NEXT_DATE = (today + timedelta(days=1)).strftime('%Y%m%d')

PREV_FILE  = f'research_report_{PREV_DATE}.html'
TODAY_FILE = f'research_report_{DATE_STR}.html'

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

    prompt = f"""今日は{DATE_JA}（{WEEKDAY}曜日）です。

最新のWeb情報を検索し、以下の要件に従ってグローバル市場分析レポートのHTMLファイルを生成してください。

━━ 分析要件 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 対象市場（大分類3つ）
  ① 株式（日本・米国）  ② 貴金属  ③ 暗号資産

■ 必ず最新情報を検索して確認すること
  - 本日の日経平均・TOPIX・東証グロース の動向・主要ニュース
  - 本日の S&P500・Nasdaq・ダウ の動向・主要ニュース
  - 直近24時間の BTC・ETH・主要アルトコイン の価格と材料
  - 金・銀・プラチナ の現在値と動向
  - 24時間以内の地政学・マクロ経済・金融政策イベント

■ 特筆銘柄（日本株10銘柄・米国株10銘柄を必ず選定）
  日本株：東証プライム・スタンダード・グロース・直近IPO・テーマ株を幅広く調査
  米国株：NYSE・NASDAQ・直近IPO・AI/半導体/防衛/バイオ等テーマ株を幅広く調査

■ 各銘柄の分析項目（全項目を確認すること）
  業績・需給・テーマ性・材料・時価総額・流動性・出来高・信用需給
  決算予定・IR・提携・政府政策・補助金・業界トレンド・チャート

■ 必須ルール
  ・「事実」「推測・予測」「リスク」を明示的に分けてバッジ/色で区別
  ・「必ず上がる」「テンバガー確定」等の買い煽り表現は絶対禁止
  ・冷静なリサーチとして記載。初心者にも分かる言葉で。
  ・末尾に銘柄を「攻め（高リスク高リターン）」「中間」「守り（ディフェンシブ）」の3タイプに分類
  ・投資は自己責任である旨の免責事項を末尾に記載

━━ ナビゲーションバー（必須・先頭と末尾の両方に配置） ━━━━━━━

以下のHTMLをレポート先頭（<body>直後）と末尾（</body>直前）の両方に配置:

<nav class="rpt-nav">
  <a {prev_nav} class="nav-btn nav-prev">← 前日</a>
  <a href="index.html" class="nav-btn nav-idx">📋 一覧</a>
  <a class="nav-btn nav-next" id="nav-next" data-placeholder="true" style="opacity:0.35;pointer-events:none;">翌日 →</a>
</nav>

━━ デザイン要件 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - ダークテーマ（背景: #0b0e14）
  - 高品質プロフェッショナルデザイン（カード・バッジ・テーブル・メータバー等のUIを使用）
  - スマートフォンでも読みやすいレスポンシブ対応（max-width: 1000px, padding等を適切に）
  - 事実：緑バッジ、推測：黄バッジ、リスク：赤バッジで視覚的に区別
  - <style>にナビゲーションCSSを必ず含めること:
    .rpt-nav{{display:flex;gap:10px;flex-wrap:wrap;padding:12px 16px;background:#111827;border:1px solid #263352;border-radius:8px;margin-bottom:20px;}}
    .nav-btn{{padding:8px 18px;border-radius:6px;font-size:12px;font-weight:700;text-decoration:none;transition:opacity .2s;}}
    .nav-prev,.nav-next{{background:#1d4ed8;color:#fff;}}
    .nav-idx{{background:#374151;color:#e8edf5;}}
    .nav-btn:hover{{opacity:.8;}}

━━ 出力形式 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<!DOCTYPE html> から </html> までの完全なHTMLのみを出力してください。
コードブロック（```）・説明文・前置き・後書きは一切不要です。HTMLのみ。"""

    print(f"[API] Calling claude-sonnet-4-6 with web_search (max 15 uses)...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
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
    )

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
    for f in sorted(BASE_DIR.glob('research_report_????????.html'), reverse=True):
        d_str = f.stem.replace('research_report_', '')
        try:
            d = datetime.strptime(d_str, '%Y%m%d').replace(tzinfo=JST)
            reports.append({
                'date_str': d_str,
                'display':  d.strftime('%Y年%m月%d日'),
                'weekday':  '月火水木金土日'[d.weekday()],
                'file':     f.name,
                'is_new':   d_str == DATE_STR,
            })
        except ValueError:
            pass

    rows = ""
    for r in reports:
        badge = '<span class="badge-new">NEW</span>' if r['is_new'] else ''
        rows += (
            f'\n      <tr data-date="{r["date_str"]}">'
            f'<td><a href="{r["file"]}">{r["display"]}（{r["weekday"]}）{badge}</a></td>'
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

    # 2. 保存
    report_path.write_text(html, encoding='utf-8')
    print(f"[OUT] Saved: {TODAY_FILE} ({len(html):,} chars)")

    # 3. 前日レポートの「翌日 →」リンクを有効化
    activate_next_link_in_prev()

    # 4. index.html 再生成
    rebuild_index()

    print("=== Complete ===")


if __name__ == '__main__':
    main()
