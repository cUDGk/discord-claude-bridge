#!/usr/bin/env python3
"""bridge セッション専用の resume ピッカー（PC側）。

背景: bridge は `claude -p`（ヘッドレス）でセッションを作る。Claude Code のネイティブ
`/resume`・`claude --resume` ピッカーは各レコードの出自タグ(entrypoint/promptSource)で
対話セッションだけを一覧し、`-p` 由来 (sdk-cli/sdk) を除外する。bot.py がこのタグを
cli/typed に自動 promote するのでネイティブピッカーにも出るが、このスクリプトは
「bridge セッションだけを手早く一覧して番号で resume したい」時の代替。

sessions.json が追跡している bridge セッションを新しい順に並べ、番号で選ぶと
`claude --resume <id>` を“元の cwd から”起動する。ID 指定 resume は cwd スコープなので、
記録された cwd で開かないと `No conversation found` になる点に対応している。

使い方:
  python resume.py          一覧を出して番号で選んで resume
  python resume.py --list   一覧だけ表示（resume しない）
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SESSIONS_JSON = BASE / "sessions.json"
PROJECTS = Path.home() / ".claude" / "projects"

# 巨大な assistant 行を json.loads せずに済むよう、必要な値だけ正規表現で拾う
RE_CWD = re.compile(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"')
RE_TITLE = re.compile(r'"aiTitle"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _unescape(s: str) -> str:
    # JSON 文字列としてデコード（\\ や \uXXXX を元に戻す）
    try:
        return json.loads(f'"{s}"')
    except json.JSONDecodeError:
        return s


def scan(path: Path) -> tuple[str | None, str | None]:
    """セッションファイルから (cwd, 最新aiTitle) を取り出す。"""
    cwd = None
    title = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if cwd is None and '"cwd"' in line:
                m = RE_CWD.search(line)
                if m:
                    cwd = _unescape(m.group(1))
            if '"aiTitle"' in line:
                m = RE_TITLE.search(line)
                if m:
                    title = _unescape(m.group(1))  # 最後に出たものを採用
    return cwd, title


def collect() -> list[dict]:
    if not SESSIONS_JSON.exists():
        sys.exit(f"sessions.json が見つかりません: {SESSIONS_JSON}")
    sids = set(json.loads(SESSIONS_JSON.read_text(encoding="utf-8")).values())

    # sid -> ファイルパス（全プロジェクトディレクトリを横断）
    found = {}
    for d in PROJECTS.iterdir() if PROJECTS.exists() else []:
        if not d.is_dir():
            continue
        for sid in sids:
            if sid in found:
                continue
            fp = d / f"{sid}.jsonl"
            if fp.exists():
                found[sid] = fp

    rows = []
    for sid, fp in found.items():
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            continue
        cwd, title = scan(fp)
        rows.append({
            "sid": sid,
            "mtime": mtime,
            "date": datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M"),
            "cwd": cwd or str(Path.home()),
            "title": title or "(タイトルなし)",
        })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def main():
    rows = collect()
    if not rows:
        sys.exit("生きている bridge セッションがありません（保持期限切れで削除された可能性）。")

    print("bridge セッション（新しい順）:\n")
    for i, r in enumerate(rows, 1):
        print(f"  {i:>2}. {r['date']}  {r['title']}")
        print(f"      {r['sid']}  [{r['cwd']}]")

    if "--list" in sys.argv:
        return

    try:
        choice = input("\n番号を選択 (q=中止): ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if choice.lower() in ("", "q"):
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(rows)):
        sys.exit("無効な番号です。")

    r = rows[int(choice) - 1]
    print(f"\nresume: {r['sid']}  (cwd: {r['cwd']})\n")
    # claude の TUI に端末を引き渡す（cwd を合わせないと ID resume が通らない）
    subprocess.run(["claude", "--resume", r["sid"]], cwd=r["cwd"])


if __name__ == "__main__":
    main()
