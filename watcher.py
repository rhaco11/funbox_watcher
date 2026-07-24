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
import
