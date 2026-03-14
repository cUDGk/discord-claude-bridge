"""
Twitterメディアツイート一覧 Web UI

方法1: syndication API (ログイン不要、一部アカウント非対応)
方法2: gallery-dl --cookies-from-browser (ブラウザのCookieを自動抽出、全アカウント対応)

使い方:
    pip install flask requests beautifulsoup4 gallery-dl
    python twitter_media.py
    → http://localhost:5000
"""

import json
import subprocess

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, render_template_string, request, jsonify, stream_with_context

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Twitter Media Viewer</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, sans-serif; background: #0f1419; color: #e7e9ea; min-height: 100vh; }
  .container { max-width: 700px; margin: 0 auto; padding: 24px 16px; }
  h1 { font-size: 1.4rem; margin-bottom: 20px; }
  .search-box { display: flex; gap: 8px; margin-bottom: 24px; }
  .search-box input {
    flex: 1; padding: 10px 14px; border-radius: 9999px; border: 1px solid #333;
    background: #202327; color: #e7e9ea; font-size: 1rem; outline: none;
  }
  .search-box input:focus { border-color: #1d9bf0; }
  .search-box button {
    padding: 10px 20px; border-radius: 9999px; border: none;
    background: #1d9bf0; color: #fff; font-weight: bold; cursor: pointer; font-size: 0.95rem;
  }
  .search-box button:disabled { opacity: 0.5; cursor: not-allowed; }
  .stop-btn { background: #f4212e !important; }
  #status { color: #71767b; margin-bottom: 16px; font-size: 0.9rem; }
  #method { color: #536471; font-size: 0.8rem; margin-bottom: 12px; }
  .tweet {
    border-bottom: 1px solid #2f3336; padding: 14px 0;
    animation: fadeIn 0.15s ease-in;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .tweet a { color: #1d9bf0; text-decoration: none; font-size: 0.95rem; }
  .tweet a:hover { text-decoration: underline; }
  .tweet .meta { color: #71767b; font-size: 0.82rem; margin-top: 2px; }
  .tweet .content {
    color: #e7e9ea; font-size: 0.9rem; margin-top: 4px;
    white-space: pre-wrap; word-break: break-word;
  }
</style>
</head>
<body>
<div class="container">
  <h1>Twitter Media Viewer</h1>
  <div class="search-box">
    <input id="username" type="text" placeholder="ユーザー名 (例: elonmusk)" autofocus
           onkeydown="if(event.key==='Enter')search()">
    <button id="btn" onclick="search()">取得</button>
  </div>
  <div id="method"></div>
  <div id="status"></div>
  <div id="results"></div>
</div>
<script>
let tweetCount = 0;
let seenIds = new Set();
let abortCtrl = null;

async function search() {
  const input = document.getElementById('username');
  const btn = document.getElementById('btn');
  const status = document.getElementById('status');
  const method = document.getElementById('method');
  const results = document.getElementById('results');
  const username = input.value.trim().replace(/^@/, '');
  if (!username) return;

  if (abortCtrl) {
    abortCtrl.abort();
    abortCtrl = null;
    btn.textContent = '取得';
    btn.classList.remove('stop-btn');
    status.textContent = `中断 (${tweetCount}件取得済み)`;
    return;
  }

  tweetCount = 0;
  seenIds.clear();
  results.innerHTML = '';
  method.textContent = '';
  btn.textContent = '停止';
  btn.classList.add('stop-btn');
  status.textContent = `@${username} 取得中...`;

  abortCtrl = new AbortController();

  try {
    const res = await fetch('/api/media/stream?username=' + encodeURIComponent(username), {
      signal: abortCtrl.signal
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const lines = buf.split('\\n');
      buf = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6);
        if (payload === '[DONE]') continue;
        if (payload.startsWith('[METHOD]')) {
          method.textContent = payload.slice(8);
          continue;
        }
        if (payload.startsWith('[ERROR]')) {
          status.textContent = 'エラー: ' + payload.slice(7);
          continue;
        }
        try {
          const tweet = JSON.parse(payload);
          if (!seenIds.has(tweet.tweet_id)) {
            seenIds.add(tweet.tweet_id);
            tweetCount++;
            status.textContent = `@${username} 取得中... ${tweetCount}件`;
            appendTweet(tweet, results);
          }
        } catch {}
      }
    }

    status.textContent = tweetCount
      ? `${tweetCount} 件のメディア付きツイート`
      : 'メディア付きツイートが見つかりませんでした';
  } catch (e) {
    if (e.name !== 'AbortError') status.textContent = 'エラー: ' + e.message;
  } finally {
    abortCtrl = null;
    btn.textContent = '取得';
    btn.classList.remove('stop-btn');
  }
}

function appendTweet(t, container) {
  const div = document.createElement('div');
  div.className = 'tweet';
  const date = t.date ? t.date.substring(0, 30) : '';
  const content = t.content ? t.content.substring(0, 200) : '';
  const mediaInfo = t.media_types ? t.media_types.join(', ') + ` (${t.media_count}件)` : `${t.media_count}件`;
  div.innerHTML = `
    <a href="${esc(t.tweet_url)}" target="_blank" rel="noopener">${esc(t.tweet_url)}</a>
    <div class="meta">${esc(date)} · ${esc(mediaInfo)}</div>
    ${content ? `<div class="content">${esc(content)}</div>` : ''}`;
  container.appendChild(div);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
</script>
</body>
</html>
"""


SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}"


def try_syndication(username: str) -> list[dict] | None:
    """syndication API で取得を試みる。取れなければ None を返す。"""
    try:
        r = requests.get(SYNDICATION_URL.format(username), timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None

    data = json.loads(script.string)
    entries = data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
    if not entries:
        return None

    tweets = []
    for entry in entries:
        tweet = entry.get("content", {}).get("tweet", {})
        if not tweet:
            continue
        media_list = tweet.get("extended_entities", {}).get("media", [])
        if not media_list:
            media_list = tweet.get("entities", {}).get("media", [])
        if not media_list:
            continue

        tid = tweet.get("id_str", "")
        screen_name = tweet.get("user", {}).get("screen_name", username)
        media_types = list(dict.fromkeys(m.get("type", "unknown") for m in media_list))

        tweets.append({
            "tweet_id": tid,
            "tweet_url": f"https://x.com/{screen_name}/status/{tid}",
            "date": tweet.get("created_at", ""),
            "content": tweet.get("full_text", tweet.get("text", "")),
            "media_count": len(media_list),
            "media_types": media_types,
        })

    tweets.sort(key=lambda t: t["tweet_id"], reverse=True)
    return tweets if tweets else None


def gallery_dl_stream(username: str):
    """gallery-dl でブラウザCookie自動抽出してストリーミング取得。"""
    url = f"https://x.com/{username}/media"
    cmd = [
        "gallery-dl", url, "--dump-json",
        "--cookies-from-browser", "chrome",
        "--sleep", "0.5-1.5",
    ]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        yield None, "gallery-dl がインストールされていません"
        return

    seen = {}
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if isinstance(entry, list) and len(entry) >= 2:
                meta = entry[1] if isinstance(entry[1], dict) else {}
            elif isinstance(entry, dict):
                meta = entry
            else:
                continue

            tweet_id = str(meta.get("tweet_id", ""))
            if not tweet_id:
                continue

            if tweet_id not in seen:
                seen[tweet_id] = {
                    "tweet_id": tweet_id,
                    "date": str(meta.get("date", "")),
                    "content": meta.get("content", meta.get("description", "")),
                    "tweet_url": f"https://x.com/{username}/status/{tweet_id}",
                    "media_count": 1,
                    "media_types": [],
                }
                yield seen[tweet_id], None
            else:
                seen[tweet_id]["media_count"] += 1
        except json.JSONDecodeError:
            continue

    proc.wait()
    stderr = proc.stderr.read()
    if not seen and stderr:
        yield None, stderr[:500]


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/media/stream")
def api_media_stream():
    username = request.args.get("username", "").strip().lstrip("@")
    if not username:
        return jsonify(error="ユーザー名を指定してください"), 400

    def generate():
        # まず syndication API を試す
        yield "data: [METHOD]syndication API で取得中...\n\n"
        tweets = try_syndication(username)

        if tweets:
            yield f"data: [METHOD]syndication API ({len(tweets)}件)\n\n"
            for t in tweets:
                yield f"data: {json.dumps(t, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        # フォールバック: gallery-dl (ブラウザCookie自動抽出)
        yield "data: [METHOD]gallery-dl (ブラウザCookie自動抽出) で取得中...\n\n"
        count = 0
        for tweet, error in gallery_dl_stream(username):
            if error:
                yield f"data: [ERROR]{error}\n\n"
                break
            if tweet:
                count += 1
                yield f"data: {json.dumps(tweet, ensure_ascii=False)}\n\n"

        if count > 0:
            yield f"data: [METHOD]gallery-dl ({count}件)\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    print("http://localhost:5000 で起動中...")
    app.run(host="0.0.0.0", port=5000, debug=False)
