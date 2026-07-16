# Funbox 新品監控小工具（Mac 版）

## 這東西在做什麼

定期抓取你指定的商城分類頁，把「目前的商品清單」跟「上次記錄的清單」比對，
一旦出現新的商品連結，就透過 Telegram Bot 立刻通知你。

適用於 Cyberbiz 平台的商店（例如 shop.funbox.com.tw），理論上也適用其他用
同一套系統的分類頁，只要把網址換掉即可。

**技術備註**：這個網站的商品清單是用 JavaScript 動態載入的（一般的
`requests` 抓不到），所以這版改用 Playwright 開一個背景執行的無頭瀏覽器，
真的把頁面載入、等 JS 跑完後再讀取畫面內容，跟你自己用瀏覽器打開看到的
結果一致，也比較不怕網站改版把 API 結構換掉。

---

## 第一次設定（只需做一次）

### 1. 安裝需要的 Python 套件

打開「終端機」（Terminal），輸入：

```bash
cd 這個資料夾的路徑
pip3 install -r requirements.txt
```

> 如果你的 Mac 是用 `python3` / `pip3`，指令跟上面一樣即可。
> 如果出現權限錯誤，可以在指令後面加上 `--user`。

### 1.5. 安裝 Playwright 的瀏覽器引擎（重要，多這一步）

Playwright 這個套件本身不含瀏覽器，裝好套件後還要再下載一次無頭瀏覽器：

```bash
python3 -m playwright install chromium
```

這會下載一個 Chromium 瀏覽器到本機（第一次會花一點時間，約 100~200MB），
裝完之後才能正常執行 `watcher.py`。這個步驟只需要做一次。

### 2. 填寫設定檔

打開 `config.json`，把以下兩項換成你自己的資料：

```json
{
  "telegram_bot_token": "你的 Bot Token",
  "telegram_chat_id": "你的 Chat ID",
  "watch_targets": [
    {
      "name": "戰鬥陀螺",
      "url": "https://shop.funbox.com.tw/collections/%E6%88%B0%E9%AC%A5%E9%99%80%E8%9E%BA"
    }
  ]
}
```

- `telegram_bot_token`：跟 @BotFather 申請到的那串
- `telegram_chat_id`：你剛剛用 getUpdates 查到的那個數字（例如 994463392）
- `watch_targets`：想監控的分類頁清單，**可以加超過一個**，例如：

```json
"watch_targets": [
  { "name": "戰鬥陀螺", "url": "https://shop.funbox.com.tw/collections/戰鬥陀螺" },
  { "name": "LEGO樂高", "url": "https://shop.funbox.com.tw/collections/lego" }
]
```

### 3. 手動先跑一次，確認可以動

```bash
python3 watcher.py
```

第一次執行**不會發通知**，因為程式會先建立「目前有哪些商品」的基準記錄
（存在 `state/` 資料夾裡），避免把現有商品全部誤判成新品轟炸你。

看到類似這樣的訊息代表成功：

```
[2026-07-13 21:00:00] 檢查中：戰鬥陀螺 (https://shop.funbox.com.tw/collections/...)
[2026-07-13 21:00:01] 首次執行，已建立基準（共 2 件商品），之後才會通知新品。
```

### 4. 再跑第二次，測試通知有沒有正常送達（選擇性）

你可以先手動刪除 `state/` 資料夾裡對應的檔案再跑一次，模擬「有新商品」的情況，
確認手機真的有收到 Telegram 通知，測試完再讓它照正常排程跑就好。

---

## 設定自動定期執行（cron）

1. 打開終端機，輸入 `crontab -e`（第一次可能會問你要用哪個編輯器，選 nano 最簡單）
2. 在最後一行加入（**請把路徑換成你實際存放這個資料夾的完整路徑**）：

```
*/5 * * * * cd /Users/你的使用者名稱/funbox-watcher && /usr/bin/python3 watcher.py >> cron.log 2>&1
```

這代表**每 5 分鐘執行一次**。可以依照商品搶手程度調整頻率（例如改成 `*/2` 代表每 2 分鐘）。

3. 存檔離開（nano 是按 `Ctrl+O` 存檔、`Ctrl+X` 離開）
4. 確認排程已加入：

```bash
crontab -l
```

> 注意：cron 執行時的 Python 路徑可能跟你終端機用的不同，如果沒有動靜，
> 可以先用 `which python3` 查出正確路徑，替換上面指令中的 `/usr/bin/python3`。

---

## 常見問題

**Q: 執行後說找不到 requests 或 playwright？**
代表套件沒裝進 cron 實際會用到的那個 Python 環境，回到步驟1重新確認用的是同一個 `pip3`。

**Q: 執行後說找不到瀏覽器執行檔（Executable doesn't exist）？**
代表忘記做步驟 1.5，回去執行 `python3 -m playwright install chromium`。

**Q: 第一次手動測試跑很久都沒結束？**
屬正常現象，Playwright 需要真的載入頁面等 JS 跑完，通常 5~15 秒內會結束，如果超過 30 秒沒反應，可能是網路問題，可以按 `Ctrl+C` 中斷後重試一次。

---

## 進階：搬到 GitHub Actions 上跑（不需要 Mac 一直開機）

如果不想讓 Mac 一直保持開機、不睡眠，可以把這套監控腳本搬到 **GitHub Actions**
上執行——完全免費，GitHub 的伺服器本來就 24 小時開著，不需要自己管理。

### 運作方式

- 程式碼放到一個 GitHub repo（可以設成 Private，只有你看得到）
- Telegram Token / Chat ID **不寫進檔案**，改存成 GitHub 的加密 Secrets
- `.github/workflows/watch.yml` 這個檔案定義排程，每 5 分鐘自動觸發一次
  （GitHub Actions 排程最小間隔是 5 分鐘，且系統忙碌時可能會延遲幾分鐘才觸發，
  這是 GitHub 的限制，沒有辦法做到像本機 cron 一樣精準每分鐘）
- 每次執行完，最新的「已看過商品」記錄會自動 commit 回這個 repo，
  這樣下次執行才能正確比對出新商品

### 設定步驟

**1. 建立 GitHub 帳號跟新 repo**（如果還沒有帳號）

到 [github.com](https://github.com) 註冊，登入後點右上角 `+` → `New repository`，
名稱隨意（例如 `funbox-watcher`），**建議設成 Private**，不用勾選任何初始化選項，建立。

**2. 把這個資料夾推上去**

在終端機、這個資料夾底下執行（`你的repo網址` 換成 GitHub 給你的網址，
建立完 repo 後頁面上會顯示）：

```bash
git init
git add .
git commit -m "初始化監控腳本"
git branch -M main
git remote add origin 你的repo網址
git push -u origin main
```

> 如果是第一次用 Git，執行 `git push` 時可能會要你登入 GitHub 帳號授權，
> 照畫面指示做就好（通常會跳出瀏覽器頁面讓你登入）。

**3. 設定 Secrets（把 Token 安全地交給 GitHub，而不是寫進程式碼）**

到你的 repo 頁面 → `Settings` → 左側選單 `Secrets and variables` → `Actions`
→ 點 `New repository secret`，新增兩筆：

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 你的 Bot Token |
| `TELEGRAM_CHAT_ID` | 你的 Chat ID（例如 994463392） |

**4. 手動觸發一次，測試流程是否正常**

到 repo 頁面上方 `Actions` 分頁，左側選 `新品監控`，右邊會有一個
`Run workflow` 按鈕，點下去手動觸發一次。等個一兩分鐘，點進這次執行紀錄，
確認每個步驟前面都是綠色勾勾（尤其是「執行監控腳本」那步），
代表跑成功了。第一次執行一樣只會建立基準，不會發通知。

**5. 之後就完全自動了**

不需要再做任何事，GitHub 會每 5 分鐘自動幫你檢查一次，Mac 完全不需要開機。
如果之後想調整監控的網址，只要編輯 repo 裡的 `config.json`（改完
`git add . && git commit -m "更新監控目標" && git push` 推上去就好），
不需要碰 Mac 上原本那份。

### 這樣設定後，Mac 上的 cron 還需要留著嗎？

不需要了，可以移除，避免同時被兩邊監控、重複發送通知。移除方式：

```bash
crontab -r
```

（這會清空所有排程，如果你還有其他不相關的排程，建議用 `crontab -e` 手動刪除
特定那行，而不是整個清空）

### 常見問題（GitHub Actions 版）

**Q: Actions 分頁裡完全沒有排程自動執行，只有手動觸發過的？**
GitHub 對完全沒有任何 commit 活動的 repo，排程可能需要等第一次手動觸發或
push 後才會開始生效，先手動跑一次（`Run workflow`）通常就會正常開始排程。

**Q: 執行紀錄顯示紅色叉叉（失敗）？**
點進去看是哪個步驟失敗，最常見是 Secrets 名稱打錯（要跟 workflow 檔案裡的
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 完全一樣，大小寫也要對），
或是 `git push` 那步失敗（通常是 repo 的 Actions 權限沒開，到
`Settings → Actions → General → Workflow permissions` 確認選的是
`Read and write permissions`）。

**Q: 60 天沒有任何活動，排程會被 GitHub 自動關閉，這是真的嗎？**
是的，這是 GitHub 的機制，避免資源浪費。只要這個監控腳本持續有新商品出現、
狀態記錄有被更新 commit，就不會觸發這個限制；如果分類頁長期都是 0 件商品、
完全沒有變化，記得每隔一陣子上去手動點一次 `Run workflow` 保持活躍。

**Q: 想監控的網址怎麼找？**
到官網分類頁，選好篩選條件（例如依上架時間排序）後，複製瀏覽器網址列的完整網址貼進 `watch_targets` 即可。

**Q: 商品名稱顯示「名稱擷取失敗」？**
代表該網站的 HTML 結構跟預期不同，不影響通知本身，你還是會收到商品連結可以直接點擊查看。如果常常發生，把 log.txt 內容給我，我可以幫你調整擷取邏輯。

**Q: 想要幾秒內就搶到，5分鐘會不會太慢？**
可以把 cron 頻率調到 `* * * * *`（每分鐘），但要注意頻率太高有可能被網站判定為異常流量而暫時擋掉，建議先從 3~5 分鐘開始測試穩定度。
