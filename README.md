# Market Pulse

A live stock &amp; crypto news aggregator. A GitHub Actions cron job polls ~30
publisher RSS feeds plus per-region/per-topic Google News search feeds every
30 minutes, dedupes and classifies the results, and writes `data/news.json`.
A static page (`index.html` / `app.js`) reads that file client-side — no
backend server, hosted on GitHub Pages.

- `scripts/fetch_news.py` — the polling/classification job (stdlib + `feedparser`)
- `.github/workflows/update-news.yml` — runs the job on a schedule and commits the result
- `data/news.json` — generated output, committed by the bot
- `index.html`, `app.js` — the frontend

Live at https://kranmal.github.io/market-pulse/
