#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
funbox-watcher / 通用版商品分類頁監控腳本
------------------------------------------------
用途：定期檢查 config.json 裡列出的分類頁網址，
      發現有「之前沒看過的商品」就透過 Telegram Bot 發通知。

用法：
    python3 watcher.py
    TARGET_ID=xxx python3 watcher.py   # 只跑指定的單一目標

建議：透過 cron（Mac/Linux）或工作排程器（Windows）定期執行，
      不需要腳本自己常駐背景。
"""

import json
import os
import re
import sys
import hashlib
import urllib.parse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_DIR = os.path.join(BASE_DIR, "state")
LOG_PATH = os.path.join(BASE_DIR, "watcher.log")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_LINK_REGEX = r"/product"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        log(f"找不到設定檔：{CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def state_file_for(url: str) -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(STATE_DIR, f"{key}.json")


def load_previous_products(url: str):
    path = state_file_for(url)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_current_products(url: str, products: dict):
    path = state_file_for(url)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def fetch_products(url: str, link_regex: str = DEFAULT_LINK_REGEX, debug: bool = False) -> dict:
    products = {}
    pattern = re.compile(link_regex)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = browser.new_page(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 2000},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            },
        )
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
            """
        )
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        def grab_anchors():
            all_links = page.eval_on_selector_all(
                "a[href]",
                """els => els.map(el => ({
                    href: el.getAttribute('href'),
                    text: el.innerText.trim()
                }))"""
            )
            return [item for item in all_links if item.get("href") and pattern.search(item["href"])]

        anchors = []
        try:
            page.wait_for_function(
                """(pattern) => {
                    const re = new RegExp(pattern);
                    return Array.from(document.querySelectorAll('a[href]'))
                        .some(a => re.test(a.getAttribute('href') || ''));
                }""",
                arg=link_regex,
                timeout=12000,
            )
            anchors = grab_anchors()
        except Exception:
            pass

        retry_waits = [5000, 8000]
        for wait_ms in retry_waits:
            if anchors:
                break
            page.wait_for_timeout(wait_ms)
            anchors = grab_anchors()

        if debug:
            debug_dir = os.path.join(BASE_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            screenshot_path = os.path.join(debug_dir, "screenshot.png")
            html_path = os.path.join(debug_dir, "page.html")
            page.screenshot(path=screenshot_path, full_page=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            log(f"除錯檔案已存到：{screenshot_path} 與 {html_path}")

        if debug:
            log(f"debug: 符合 link_regex（{link_regex}）的連結共找到 {len(anchors)} 個")

        for item in anchors:
            href = item.get("href") or ""
            full_url = urllib.parse.urljoin(url, href.split("?")[0])
            text = item.get("text") or ""
            if text:
                products[full_url] = text
            elif full_url not in products:
                products[full_url] = ""

        browser.close()

    return products


def send_telegram_message(token: str, chat_id: str, text: str):
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        api_url,
        data={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        log(f"Telegram 發送失敗：{resp.status_code} {resp.text}")
    else:
        log("Telegram 通知已送出")


def fetch_stock_status(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    availability = None
    tag = soup.find("meta", attrs={"name": "product:availability"}) or \
          soup.find("meta", attrs={"property": "product:availability"})
    if tag and tag.get("content"):
        availability = tag["content"].strip().lower()

    title = None
    title_tag = soup.find("meta", attrs={"name": "og:title"}) or \
                soup.find("meta", attrs={"property": "og:title"})
    if title_tag and title_tag.get("content"):
        title = title_tag["content"].strip()

    return {"availability": availability, "title": title or url}


def check_stock_target(target: dict, token: str, chat_ids: list):
    name = target.get("name", "未命名商品")
    url = target["url"]
    log(f"檢查補貨狀態：{name} ({url})")

    try:
        current = fetch_stock_status(url)
    except Exception as e:
        log(f"抓取失敗：{e}")
        return

    if current["availability"] is None:
        log("這次抓不到庫存標籤，可能是網站結構改變，請檢查。")
        return

    log(f"目前庫存狀態：{current['availability']}")

    previous = load_previous_products(url)

    if previous is None:
        save_current_products(url, current)
        log(f"首次執行，已記錄目前庫存狀態（{current['availability']}），之後狀態變成有貨才會通知。")
        return

    was_out_of_stock = previous.get("availability") not in ("instock", "in stock")
    is_now_in_stock = current["availability"] in ("instock", "in stock")

    if was_out_of_stock and is_now_in_stock:
        log("偵測到補貨！")
        message = f"📦【{name}】補貨了！\n\n{current['title']}\n{url}"
        for chat_id in chat_ids:
            send_telegram_message(token, chat_id, message)
    else:
        log("庫存狀態沒有變化（或本來就有貨，不算補貨事件）。")

    save_current_products(url, current)


def check_target(target: dict, token: str, chat_ids: list, debug: bool = False):
    name = target.get("name", "未命名分類")
    url = target["url"]
    link_regex = target.get("link_regex", DEFAULT_LINK_REGEX)
    log(f"檢查中：{name} ({url})")

    try:
        current_products = fetch_products(url, link_regex=link_regex, debug=debug)
    except Exception as e:
        log(f"抓取失敗：{e}")
        return

    if not current_products:
        log("這次抓到 0 件商品（可能是分類本身目前真的沒有商品，也可能是抓取被擋或 link_regex 沒對到，建議偶爾用 --debug 確認）。")

    previous_products = load_previous_products(url)

    if previous_products is None:
        save_current_products(url, current_products)
        log(f"首次執行，已建立基準（共 {len(current_products)} 件商品），之後才會通知新品。")
        return

    new_urls = [u for u in current_products if u not in previous_products]

    if new_urls:
        log(f"發現 {len(new_urls)} 件新商品！")
        lines = [f"🆕【{name}】發現新商品！\n"]
        for u in new_urls:
            title = current_products[u] or "(名稱擷取失敗，點連結查看)"
            lines.append(f"• {title}\n{u}")
        message = "\n\n".join(lines)
        for chat_id in chat_ids:
            send_telegram_message(token, chat_id, message)
    else:
        log("沒有新商品。")

    save_current_products(url, current_products)


def main():
    config = load_config()

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram_bot_token", "")
    raw_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("telegram_chat_id", "")
    chat_ids = [c.strip() for c in str(raw_chat_id).split(",") if c.strip()]
    targets = config.get("watch_targets", [])

    if not token or "在這裡貼上" in token:
        log("尚未設定 telegram_bot_token（環境變數 TELEGRAM_BOT_TOKEN 或 config.json 皆可），請先設定。")
        sys.exit(1)
    if not chat_ids:
        log("尚未設定 telegram_chat_id（環境變數 TELEGRAM_CHAT_ID 或 config.json 皆可），請先設定。")
        sys.exit(1)
    if not targets:
