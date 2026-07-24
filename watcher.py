#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
funbox-watcher / 通用版 Cyberbiz 商品分類頁監控腳本
------------------------------------------------
用途：定期檢查 config.json 裡列出的分類頁網址，
      發現有「之前沒看過的商品」就透過 Telegram Bot 發通知。

用法：
    python3 watcher.py

建議：透過 cron（Mac/Linux）或工作排程器（Windows）定期執行，
      不需要腳本自己常駐背景。
"""

import json
import os
import sys
import hashlib
import urllib.parse
from datetime import datetime

import requests
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
    """每個監控網址對應一個獨立的狀態檔，用網址的 hash 當檔名避免特殊字元問題"""
    os.makedirs(STATE_DIR, exist_ok=True)
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(STATE_DIR, f"{key}.json")


def load_previous_products(url: str):
    path = state_file_for(url)
    if not os.path.exists(path):
        return None  # 代表第一次執行，尚無基準
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_current_products(url: str, products: dict):
    path = state_file_for(url)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def fetch_products(url: str, debug: bool = False) -> dict:
    """
    用 Playwright 開一個無頭瀏覽器實際載入頁面，
    等 JavaScript 把商品資料畫出來後，再讀取當下的 DOM，
    回傳 {商品網址: 商品名稱} 的字典。

    debug=True 時，會把當下畫面截圖與完整 HTML 存到 debug/ 資料夾，方便排查。
    """
    products = {}

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
        # 隱藏掉幾個常見的「這是自動化瀏覽器」技術特徵，
        # 有些網站會檢查這些屬性來判斷是否為機器人
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
            """
        )
        try:
            page.goto(url, timeout=30000, wait_until="networkidle")
        except Exception:
            # networkidle 有時等不到（例如有背景輪詢），改用較寬鬆的等待方式
            page.goto(url, timeout=30000, wait_until="load")
            page.wait_for_timeout(3000)  # 額外等 3 秒讓 JS 渲染完成

        # 保險起見，再多等一下，確保商品區塊真的渲染完成
        page.wait_for_timeout(2500)

        anchors = page.eval_on_selector_all(
            "a[href*='/product']",
            """els => els.map(el => ({
                href: el.getAttribute('href'),
                text: el.innerText.trim()
            }))"""
        )

        # 有些網站（例如商品資料是額外用比較慢的背景請求載入）
        # 第一次抓的時候畫面可能還在轉圈圈、商品還沒跑出來，
        # 這裡多等一段時間後重試一次，避免誤判成「沒有商品」
        if not anchors:
            page.wait_for_timeout(5000)
            anchors = page.eval_on_selector_all(
                "a[href*='/product']",
                """els => els.map(el => ({
                    href: el.getAttribute('href'),
                    text: el.innerText.trim()
                }))"""
            )

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
            log(f"debug: a[href*='/product'] 選擇器共找到 {len(anchors)} 個元素")

        for item in anchors:
            href = item.get("href") or ""
            if "/product" not in href:
                continue
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


def check_target(target: dict, token: str, chat_ids: list, debug: bool = False):
    name = target.get("name", "未命名分類")
    url = target["url"]
    log(f"檢查中：{name} ({url})")

    try:
        current_products = fetch_products(url, debug=debug)
    except Exception as e:
        log(f"抓取失敗：{e}")
        return

    if not current_products:
        log("這次抓到 0 件商品（可能是分類本身目前真的沒有商品，也可能是抓取被擋，建議偶爾用 --debug 確認）。")

    previous_products = load_previous_products(url)

    if previous_products is None:
        # 第一次執行，只建立基準，不發通知（避免把現有商品都當成新品轟炸你）
        # 就算這次是 0 件商品，也要正常存檔，這樣之後才會正確比對出「新商品」
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

    # 優先讀取環境變數（給 GitHub Actions 等雲端環境用 Secrets 注入），
    # 本機執行時如果沒有設環境變數，就退回讀取 config.json 裡的值。
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram_bot_token", "")
    raw_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("telegram_chat_id", "")
    # 支援多個 Chat ID，用逗號分隔（例如 "111111,222222,333333"），
    # 每個朋友各自跟 bot 私聊拿到自己的 Chat ID 後加進這個清單即可。
    chat_ids = [c.strip() for c in str(raw_chat_id).split(",") if c.strip()]
    targets = config.get("watch_targets", [])

    if not token or "在這裡貼上" in token:
        log("尚未設定 telegram_bot_token（環境變數 TELEGRAM_BOT_TOKEN 或 config.json 皆可），請先設定。")
        sys.exit(1)
    if not chat_ids:
        log("尚未設定 telegram_chat_id（環境變數 TELEGRAM_CHAT_ID 或 config.json 皆可），請先設定。")
        sys.exit(1)
    if not targets:
        log("config.json 的 watch_targets 是空的，沒有任何要監控的網址。")
        sys.exit(1)

    log(f"這次會通知的 Chat ID 共 {len(chat_ids)} 個。")

    debug = "--debug" in sys.argv

    for i, target in enumerate(targets):
        # debug 模式下只對第一個目標跑，並存下截圖/HTML，避免產生太多除錯檔案
        check_target(target, token, chat_ids, debug=(debug and i == 0))


if __name__ == "__main__":
    main()
