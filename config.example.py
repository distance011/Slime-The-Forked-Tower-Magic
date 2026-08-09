# -*- coding: utf-8 -*-
"""
配置模板 - 复制为 config.py 并填入你的腾讯文档登录凭证

获取方式:
1. 用浏览器登录腾讯文档并打开你的发车表
2. F12 -> 开发者工具 -> Application -> Cookies -> docs.qq.com
3. 复制 uid / uid_key / TOK 及完整 Cookie 串填入下方
"""

# 登录凭证（Cookie 过期时需重新获取）
UID = ""                      # 你的 uid
UID_KEY = ""                  # 你的 uid_key
TOK = ""                      # 你的 TOK

COOKIE = ""                   # 完整的 docs.qq.com Cookie 串

# 发车表文档信息（腾讯文档智能表格的ID）
DOC_URL = "https://docs.qq.com/smartsheet/你的文档ID"
UPID = ""                     # 文档ID (url中的 DY2...)
PADID = ""                    # 智能表格 padId
DOCID = ""                    # 全局padId (300000000$...)
SUBID = ""                    # 表格页签ID
TABLEID = ""                  # 表格ID
GENERALPACKET = {"rel_rev": "", "dver": "", "right_tag": 1}
AVATAR = ""                   # 车头头像URL(可留空)
