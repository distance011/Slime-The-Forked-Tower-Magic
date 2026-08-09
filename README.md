# 史莱姆团 - 腾讯文档发车表自动化工具

针对腾讯文档**智能表格**（史莱姆团发车表）的自动化脚本：
- 自动统计各车表名单人数并更新到发车表
- 按玩家名/QQ 查询报名了哪些车、在哪个队、打什么位置
- 提供网页查询界面

## 功能

| 脚本 | 功能 |
|---|---|
| `update_renshu.py` | 每 5 分钟读取各车表名单，统计填写 QQ 的人数，自动写入发车表「人数」列 |
| `query_renshu.py` | 命令行查询：输入玩家名或 QQ，显示所在车表、队伍、主职/副职、名单链接 |
| `web_query.py` | 网页查询界面：浏览器访问 http://localhost:8000 |

## 原理

腾讯文档的网页端把表格渲染为 Canvas，文本通过压缩的**动作流**(actions)存储。
本项目破解了该格式：解码 `fillText` 命令重建单元格网格（含坐标），从而精确识别
每个玩家所在的队伍列（A队/B队/C队/1队/2队/3队）及其主职/副职。
写入则通过 WebSocket 协作协议（socket.io）提交 `SET_RECORD_MUTATION` 变更。

> 注意：这是对腾讯文档私有协议的逆向工程，仅供学习/个人使用，请勿滥用。

## 安装

```bash
pip install websocket-client
```

## 配置

1. 复制配置模板：
   ```bash
   copy config.example.py config.py
   ```
2. 用浏览器登录腾讯文档，打开你的发车表，F12 -> Application -> Cookies
3. 把 `uid` / `uid_key` / `TOK` 和完整 Cookie 串填入 `config.py`
4. 填入发车表的文档 ID（UPID/PADID/DOCID/SUBID 等）

> `config.py` 含登录凭证，已被 `.gitignore` 排除，**切勿提交到 Git**。

## 使用

```bash
# 1. 自动更新人数（每5分钟一次）
python update_renshu.py

# 2. 命令行查询
python query_renshu.py --rebuild     # 重新扫描所有车表名单
python query_renshu.py "玩家名或QQ"

# 3. 网页查询
python web_query.py                  # 打开 http://localhost:8000
```

## 免责声明

- Cookie 会过期，失效后需重新获取
- 部分名单（如需额外登录的表）无法自动统计
- 本项目与腾讯官方无关，腾讯可能随时变更协议导致失效
