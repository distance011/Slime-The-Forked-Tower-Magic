# 史莱姆团 - 腾讯文档发车表玩家查询工具

针对腾讯文档**智能表格**（史莱姆团发车表）的玩家查询网页工具。
输入玩家名或 QQ，即可查询报名了哪些车表、在哪个队伍、打什么位置。

## 功能

- **按玩家名 / QQ 查询**：显示所在车表、时间、车头、队伍（A队/B队/C队/1队/2队/3队）、主职/副职
- **网页界面**：浏览器打开 http://localhost:8000，输入即可查询
- **命令行查询**：`python query_renshu.py "玩家名或QQ"`
- **按日期正序排列**：只显示未过期的车次
- **名单链接**：每个结果可直接跳转到对应车表的在线名单

## 原理

腾讯文档网页端把表格渲染为 Canvas，文本通过压缩的**动作流**(actions)存储。
本项目破解了该格式：解码 `fillText` 命令重建单元格网格（含坐标），从而精确识别
每个玩家所在的队伍列及其主职/副职，兼容多种名单布局（`主职-副职` / `位置/ID/主职/辅助职业` / `职业/副职` 等）。

> 注意：这是对腾讯文档私有协议的逆向工程，仅供学习/个人使用，请勿滥用。

## 文件

| 文件 | 说明 |
|---|---|
| `web_query.py` | 网页查询服务（http://localhost:8000） |
| `query_renshu.py` | 命令行查询 + 名单扫描解析 |
| `config.example.py` | 配置模板（需复制为 config.py 填写） |

## 安装

```bash
pip install websocket-client
```

## 配置

1. 复制配置模板并填写：
   ```bash
   copy config.example.py config.py
   ```
2. 用浏览器登录腾讯文档，打开发车表，F12 -> Application -> Cookies
3. 把 `uid` / `uid_key` / `TOK` 和完整 Cookie 串填入 `config.py`
4. 填入发车表的文档 ID（UPID/PADID/DOCID/SUBID 等）

> `config.py` 含登录凭证，已被 `.gitignore` 排除，**切勿提交到 Git**。

## 使用

```bash
# 1. 首次使用：扫描所有车表名单（约1-2分钟）
python query_renshu.py --rebuild

# 2. 命令行查询
python query_renshu.py "玩家名或QQ"

# 3. 启动网页查询
python web_query.py
# 浏览器打开 http://localhost:8000
```

## 免责声明

- Cookie 会过期，失效后需重新获取
- 部分名单（如需额外登录的表）无法自动统计
- 本项目与腾讯官方无关，腾讯可能随时变更协议导致失效
