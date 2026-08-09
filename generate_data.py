#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成静态查询站点数据: 从 players_db.json 生成 site/data.json
用法: python generate_data.py   (需先运行 query_renshu.py --rebuild 生成数据库)
"""

import json
import os
import sys
import time
import shutil

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "players_db.json")
SITE_DIR = os.path.join(SCRIPT_DIR, "site")
DATA_FILE = os.path.join(SITE_DIR, "data.json")


def build_site_data(db):
    """把 players_db 转为静态站点数据(仅保留查询需要的信息)"""
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "rosters": []}
    for roster in db:
        players = []
        for p in roster.get("players", []):
            if not p.get("name"):
                continue
            players.append({
                "name": p.get("name", ""),
                "qq": p.get("qq", ""),
                "team": p.get("team", ""),
                "main": p.get("main", ""),
                "sub": p.get("sub", ""),
            })
        if not players:
            continue
        out["rosters"].append({
            "label": roster.get("label") or roster.get("time") or "",
            "time": roster.get("time") or "",
            "leader": roster.get("leader") or "",
            "url": f"https://docs.qq.com/sheet/{roster.get('doc','')}?tab={roster.get('tab','')}",
            "players": players,
        })
    return out


def main():
    if not os.path.exists(DB_FILE):
        print("未找到 players_db.json！请先运行: python query_renshu.py --rebuild")
        return
    db = json.load(open(DB_FILE, encoding="utf-8"))
    data = build_site_data(db)
    os.makedirs(SITE_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    total_players = sum(len(r["players"]) for r in data["rosters"])
    print(f"已生成 {DATA_FILE}")
    print(f"  车表数: {len(data['rosters'])}, 玩家总数: {total_players}")
    # 复制静态页面
    src_html = os.path.join(SCRIPT_DIR, "site", "index.html")
    if not os.path.exists(src_html):
        print("注意: 缺少 site/index.html, 请先创建静态页面")
    else:
        print("  site/ 目录内容:", os.listdir(SITE_DIR))


if __name__ == "__main__":
    main()
