#!/usr/bin/env python3
"""Poll a curated set of worldwide stock & crypto news feeds and write data/news.json.

Sources are a mix of:
  - named publisher RSS feeds (major financial/crypto outlets across regions)
  - Google News RSS *search* feeds, scoped per-topic and per-locale, which
    themselves aggregate thousands of underlying worldwide publishers — this
    is what gives broad "worldwide" coverage without hardcoding every site.

Runs headless in a GitHub Actions cron job; no API keys required.
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

import feedparser

OUT_PATH = "data/news.json"
MAX_ITEMS_PER_FEED = 20
MAX_TOTAL_ITEMS = 400
MAX_AGE_DAYS = 5
REQUEST_TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; MarketPulseBot/1.0; +https://kranmal.github.io/market-pulse/)"

# ── Named publisher feeds ───────────────────────────────────────────────
# (url, source_name, category, region)
NAMED_FEEDS = [
    # US / global finance
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", "stocks", "US"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC Markets", "stocks", "US"),
    ("http://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch", "stocks", "US"),
    ("http://feeds.marketwatch.com/marketwatch/marketpulse/", "MarketWatch Pulse", "stocks", "US"),
    ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance", "stocks", "US"),
    ("https://www.investing.com/rss/news.rss", "Investing.com", "stocks", "Global"),
    ("https://www.economist.com/finance-and-economics/rss.xml", "The Economist", "stocks", "Global"),
    ("https://seekingalpha.com/market_currents.xml", "Seeking Alpha", "stocks", "US"),
    # UK / Europe
    ("https://www.ft.com/rss/home", "Financial Times", "stocks", "UK"),
    ("https://www.theguardian.com/uk/business/rss", "The Guardian Business", "stocks", "UK"),
    ("https://www.telegraph.co.uk/business/rss.xml", "The Telegraph Business", "stocks", "UK"),
    # Asia-Pacific
    ("https://asia.nikkei.com/rss/feed/nar", "Nikkei Asia", "stocks", "Asia"),
    ("https://www.scmp.com/rss/92/feed", "South China Morning Post Business", "stocks", "Asia"),
    ("https://www.businesstimes.com.sg/rss/singapore", "The Business Times SG", "stocks", "Asia"),
    ("https://www.moneycontrol.com/rss/marketreports.xml", "Moneycontrol Markets", "stocks", "India"),
    ("https://www.livemint.com/rss/markets", "Livemint Markets", "stocks", "India"),
    # Crypto-native
    ("https://www.coindesk.com/arc/outboundfeeds/rss", "CoinDesk", "crypto", "Global"),
    ("https://cointelegraph.com/rss", "Cointelegraph", "crypto", "Global"),
    ("https://decrypt.co/feed", "Decrypt", "crypto", "Global"),
    ("https://www.theblock.co/rss.xml", "The Block", "crypto", "Global"),
    ("https://bitcoinmagazine.com/feed", "Bitcoin Magazine", "crypto", "Global"),
    ("https://cryptoslate.com/feed/", "CryptoSlate", "crypto", "Global"),
    ("https://www.newsbtc.com/feed/", "NewsBTC", "crypto", "Global"),
    ("https://cryptopotato.com/feed/", "CryptoPotato", "crypto", "Global"),
    ("https://www.crypto-news-flash.com/feed/", "Crypto News Flash", "crypto", "Global"),
    ("https://beincrypto.com/feed/", "BeInCrypto", "crypto", "Global"),
]

# ── Google News RSS search feeds — broad worldwide net ──────────────────
# (query, category, region, hl, gl, ceid)
GNEWS_QUERIES = [
    ("stock market", "stocks", "US", "en-US", "US", "US:en"),
    ("wall street earnings", "stocks", "US", "en-US", "US", "US:en"),
    ("stock market", "stocks", "UK", "en-GB", "GB", "GB:en"),
    ("stock market", "stocks", "India", "en-IN", "IN", "IN:en"),
    ("stock market", "stocks", "Asia", "en-SG", "SG", "SG:en"),
    ("stock market", "stocks", "Australia", "en-AU", "AU", "AU:en"),
    ("aktienmarkt", "stocks", "Europe", "de-DE", "DE", "DE:de"),
    ("federal reserve interest rates", "stocks", "Global", "en-US", "US", "US:en"),
    ("bitcoin", "crypto", "Global", "en-US", "US", "US:en"),
    ("ethereum", "crypto", "Global", "en-US", "US", "US:en"),
    ("cryptocurrency regulation", "crypto", "Global", "en-US", "US", "US:en"),
    ("crypto market", "crypto", "Asia", "en-SG", "SG", "SG:en"),
]

CRYPTO_KEYWORDS = re.compile(
    r"\b(bitcoin|btc|ethereum|eth\b|crypto|blockchain|token|defi|nft|stablecoin|"
    r"altcoin|binance|coinbase|solana|dogecoin|xrp|ripple)\b",
    re.IGNORECASE,
)


def gnews_url(query, hl, gl, ceid):
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def build_feed_list():
    feeds = [(url, src, cat, region) for url, src, cat, region in NAMED_FEEDS]
    for query, cat, region, hl, gl, ceid in GNEWS_QUERIES:
        url = gnews_url(query, hl, gl, ceid)
        feeds.append((url, f"Google News: {query}", cat, region))
    return feeds


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def classify_category(title, default):
    return "crypto" if CRYPTO_KEYWORDS.search(title or "") else default


def item_key(link, title):
    basis = (link or "").strip().lower() or (title or "").strip().lower()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def parse_feed(url, source, category, region):
    try:
        raw = fetch(url)
    except Exception as e:
        print(f"  ! fetch failed for {source}: {e}", file=sys.stderr)
        return []
    parsed = feedparser.parse(raw)
    items = []
    for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = None
        for field in ("published_parsed", "updated_parsed"):
            t = entry.get(field)
            if t:
                published = datetime(*t[:6], tzinfo=timezone.utc)
                break
        if published is None:
            published = datetime.now(timezone.utc)
        real_source = source
        if source.startswith("Google News:"):
            src_tag = entry.get("source")
            if isinstance(src_tag, dict) and src_tag.get("value"):
                real_source = src_tag["value"]
            elif hasattr(entry, "source") and getattr(entry.source, "title", None):
                real_source = entry.source.title
        items.append({
            "title": title,
            "link": link,
            "source": real_source,
            "category": classify_category(title, category),
            "region": region,
            "published": published.isoformat(),
        })
    return items


def main():
    feeds = build_feed_list()
    print(f"Polling {len(feeds)} feeds…")
    by_key = {}
    for url, source, category, region in feeds:
        items = parse_feed(url, source, category, region)
        print(f"  - {source}: {len(items)} items")
        for it in items:
            key = item_key(it["link"], it["title"])
            existing = by_key.get(key)
            if existing is None or it["published"] > existing["published"]:
                by_key[key] = it
        time.sleep(0.2)  # be polite to hosts

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    fresh = [it for it in by_key.values() if datetime.fromisoformat(it["published"]) >= cutoff]
    fresh.sort(key=lambda it: it["published"], reverse=True)
    fresh = fresh[:MAX_TOTAL_ITEMS]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(fresh),
        "sources_polled": len(feeds),
        "items": fresh,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(fresh)} items to {OUT_PATH}")


if __name__ == "__main__":
    main()
