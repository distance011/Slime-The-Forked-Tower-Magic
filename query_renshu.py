#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
史莱姆团发车表 - 玩家查询工具
扫描所有车表名单，建立数据库，查询某个玩家填了哪个车表、在哪个队、什么位置
用法:
  python query_renshu.py                 # 交互式查询
  python query_renshu.py <名字或QQ>       # 直接查询
  python query_renshu.py --rebuild       # 强制重新扫描所有名单
"""

import json
import re
import sys
import time
import os
import base64
import gzip
import zlib
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "players_db.json")

# 配置(从 config.py 导入)
try:
    from config import UID, UID_KEY, TOK, COOKIE, DOC_URL, UPID, PADID, DOCID, SUBID, TABLEID
except ImportError:
    print("缺少 config.py！请复制 config.example.py 为 config.py 并填写配置。")
    raise

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ---------- 读取发车表 ----------
def opendoc():
    url = (f"https://docs.qq.com/dop-api/opendoc?tab={SUBID}&viewId=v2JKhc&u=&noEscape=1"
           f"&enableSmartsheetSplit=1&supportOptimizedVer=4&chunkCellSize=15000"
           f"&enableChunkRank=1&startrow=0&endrow=100"
           f"&id={UPID}&normal=1&outformat=1&wb=1&nowb=0"
           f"&callback=clientVarsCallback&xsrf={TOK}&t=7696f6bbbb5620acc1b88c19812adf35")
    req = urllib.request.Request(url, headers={**HEADERS, "Cookie": COOKIE, "Referer": DOC_URL})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    m = re.match(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.S)
    return json.loads(m.group(1)) if m else json.loads(text)


def decode_smartsheet(b64):
    s = b64.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    rb = base64.b64decode(s)
    for magic in (b"\x1f\x8b", b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
        if rb[:2] == magic:
            try:
                return json.loads(gzip.decompress(rb).decode("utf-8"))
            except Exception:
                try:
                    return json.loads(zlib.decompress(rb).decode("utf-8"))
                except Exception:
                    pass
    return json.loads(rb.decode("utf-8"))


def get_records():
    """读取发车表，返回 (session, [record_id, doc, tab, time, label, leader])"""
    d = opendoc()
    ccv = d["clientVars"]["collab_client_vars"]
    session = {
        "apid": ccv["apid"], "rev": ccv["rev"],
        "sid": ccv["apid"]["s"], "tid": ccv["apid"]["t"], "sig": ccv["apid"]["g"],
    }
    raw = ccv["initialAttributedText"]["text"][0]["smartsheet"]
    decoded = decode_smartsheet(raw)
    rec_data = decoded[0][1]["c"]["k2"]["k1"]
    records = []
    for rid, rv in rec_data.items():
        fields = rv.get("k1", {})
        url = ""
        v = fields.get("f4vckj")
        if v and "k8" in v:
            for o in v["k8"]:
                if isinstance(o, dict) and o.get("k3"):
                    url = o["k3"]
                    break
        if not url:
            continue
        m = re.search(r"/sheet/([A-Za-z0-9]+)", url)
        if not m:
            continue
        doc = m.group(1)
        tm = re.search(r"[?&]tab=([A-Za-z0-9]+)", url)
        tab = tm.group(1) if tm else "BB08J2"
        label = ""
        if v and "k8" in v:
            for o in v["k8"]:
                if isinstance(o, dict) and o.get("k2"):
                    label = o["k2"]
                    break
        dep_time = ""
        tv = fields.get("fkfKit")
        if tv and "k4" in tv:
            ts = tv["k4"]
            try:
                dep_time = time.strftime("%m-%d %H:%M", time.localtime(int(ts) / 1000))
            except Exception:
                pass
        leader = ""
        hv = fields.get("fHSMJO")
        if hv and "k1" in hv and isinstance(hv["k1"], list) and hv["k1"]:
            leader = hv["k1"][0].get("k2", "")
        records.append({"record_id": rid, "doc": doc, "tab": tab,
                        "time": dep_time, "label": label, "leader": leader})
    return session, records


# 职业关键词（用于区分"名字"和"职业/位置"）
JOBS = set("""骑士 盗贼 白魔 黑魔 时魔 武士 忍者 机工 舞者 诗人 召唤 赤魔 蝰蛇 远敏 近战 法系 盾奶 药师 猎人 炮手 魔剑
龙骑 龙骑士 占星 学者 贤者 镰刀 钐镰客 武僧 枪刃 绝枪 召唤师 吟游诗人 机工士 画家 自由位 辅助职业 主职 位置
坦克 主坦 副坦 T 奶 奶妈 H1 H2 H3 D1 D2 任意D 任意位置 幻术师 格斗家 弓箭手 双剑师 暗黑骑士 战士 白魔导士 学者 占星术士 武僧 龙骑士 忍者 武士 机工士 舞者 黑魔导士 召唤师 赤魔导士""".split())


def is_job_token(s):
    """判断是否为职业/位置词(含组合如'白魔/药师')"""
    if s in JOBS:
        return True
    parts = re.split(r"[/、,， ]", s)
    return len(parts) > 1 and all(p in JOBS for p in parts if p)


# ================= 基于动作流的精确网格解析 =================

def get_grid(doc, tab):
    """从SSR动作流重建网格: rows[y] = [(x, text), ...]"""
    url = f"https://docs.qq.com/sheet/{doc}?tab={tab}"
    req = urllib.request.Request(url, headers={**HEADERS, "Cookie": COOKIE})
    html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    m = re.search(r'%22actions%22:%22([^"]*?)%22,%22flyweight%22', html)
    if not m:
        return None
    actions = urllib.parse.unquote(m.group(1))
    parts = actions.split(";")
    start = html.find("%5B%22")
    end = html.find("%22%5D", start)
    texts = json.loads(urllib.parse.unquote(html[start:end + 6]))
    rows = {}
    for p in parts:
        if p.startswith("q["):
            try:
                vals = json.loads(p[1:])
                tidx, x, y = int(vals[0]), float(vals[1]), float(vals[2])
                t = texts[tidx] if 0 <= tidx < len(texts) else ""
                key = round(y)
                rows.setdefault(key, []).append((round(x, 1), t))
            except Exception:
                pass
    return rows


TEAM_NAMES = ["A队", "B队", "C队", "1队", "2队", "3队"]


def parse_grid_players(rows):
    """从网格解析玩家(自适应多种布局): [{name, main, sub, qq, team}]"""
    COL_KEY = ["主职-副职", "主职", "辅助职业", "职业", "副职", "QQ号", "QQ", "ID", "位置"]
    team_cells = []  # (y, x, name)
    col_cells = []   # (y, x, kw)
    for y in sorted(rows):
        for x, t in rows[y]:
            t = t.strip()
            if any(t.startswith(nm) for nm in TEAM_NAMES):
                team_cells.append((y, x, t))
            for kw in COL_KEY:
                if t == kw:
                    col_cells.append((y, x, kw))
    if not team_cells:
        return []

    # 按y分组(区): 同一y附近的队名属于同一表头行
    import itertools
    team_cells.sort(key=lambda c: c[0])
    sections = []
    for y, group in itertools.groupby(team_cells, key=lambda c: round(c[0] / 20)):
        sections.append(sorted(list(group), key=lambda c: c[1]))
    # 每区的表头y
    sec_headers = [min(c[0] for c in sec) for sec in sections]
    sec_headers.sort()

    players = []
    for si, sec in enumerate(sections):
        teams = []
        for y, x, t in sec:
            if not any(abs(tt - x) < 100 for tt in [tx for _, tx, _ in teams]):
                teams.append((t, x, y))
        y_lo = min(c[0] for c in sec)
        y_hi = sec_headers[si + 1] if si + 1 < len(sec_headers) else 10**9
        for idx, (tname, tx, ty) in enumerate(teams):
            block_lo = (teams[idx - 1][1] + tx) / 2 if idx > 0 else 0
            block_hi = (tx + teams[idx + 1][1]) / 2 if idx + 1 < len(teams) else block_lo + 900
            # 表头带: 队名行附近(-50 ~ +80)的列头
            band = [(yy, xx, kw) for yy, xx, kw in col_cells
                    if block_lo <= xx < block_hi and abs(yy - ty) <= 80]
            if not band:
                band = [(yy, xx, kw) for yy, xx, kw in col_cells
                        if block_lo <= xx < block_hi]
            name_x = main_x = sub_x = qq_x = None
            for yy, xx, kw in band:
                if kw == "ID":
                    name_x = xx
                elif kw == "位置" and name_x is None:
                    name_x = xx
                elif kw == "主职":
                    main_x = xx
                elif kw == "职业":
                    main_x = xx
                elif kw == "辅助职业":
                    sub_x = xx
                elif kw == "副职":
                    sub_x = xx
                elif kw == "主职-副职":
                    main_x = xx - 20
                    sub_x = xx + 57
                elif kw in ("QQ", "QQ号"):
                    qq_x = xx
            if name_x is None:
                name_x = tx
            if main_x is None and sub_x is None and qq_x is None:
                continue
            # 玩家从列头行之后开始
            y_lo = max([yy for yy, _, _ in band] + [ty])
            # 解析玩家行
            for y in sorted(rows):
                if y <= y_lo or y >= y_hi:
                    continue
                cells = sorted(rows[y])
                team_cells_y = [(x, t) for x, t in cells if block_lo <= x < block_hi and 30 <= x < 2600]
                if not team_cells_y:
                    continue
                name = main = sub = qq = ""
                for x, txt in team_cells_y:
                    txt = txt.replace("\ufffd", "").strip()
                    if not txt or txt == "进度" or txt.startswith(("填表", "备注", "过本次")):
                        continue
                    if name_x is not None and abs(x - name_x) < 60 and not name:
                        name = txt
                    elif main_x is not None and abs(x - main_x) < 55:
                        main = txt
                    elif sub_x is not None and abs(x - sub_x) < 55:
                        sub = txt
                    elif qq_x is not None and abs(x - qq_x) < 80 and re.fullmatch(r"\d{5,11}", txt):
                        qq = txt
                if name and not re.fullmatch(r"\d{1,2}", name) and not re.fullmatch(r"\d{5,11}", name):
                    p = {"name": name, "main": main, "sub": sub, "qq": qq, "team": tname}
                    if not any(ex["name"] == p["name"] and ex["team"] == p["team"] for ex in players):
                        players.append(p)
    return players

QQ_RE = re.compile(r"^\d{6,11}$")

TEAM_HEADER_RE = re.compile(r"^([ABCabc123])\s*队|^1队|^2队|^3队|^[D-F]队")


def is_qq(s):
    return bool(s and QQ_RE.match(s.strip()))


def clean(s):
    """清理 SSR 提取的乱码尾字符"""
    if not s:
        return s
    return s.replace("\ufffd", "").strip()


def extract_roster_info(cells):
    """提取车表基础信息: 时间, 车头, 副本"""
    info = {"time": "", "leader": "", "team_headers": []}
    for i, v in enumerate(cells):
        if not isinstance(v, str):
            continue
        s = clean(v)
        if s == "车头" and i + 1 < len(cells):
            info["leader"] = clean(cells[i + 1])
        if ("发车时间" in s or s == "时间") and info["time"] == "":
            # 时间后面可能有多个格子
            parts = []
            for j in range(i + 1, min(i + 4, len(cells))):
                c = clean(cells[j])
                if not c or ":" in c or re.match(r"^\d{4}/\d", c):
                    parts.append(c)
                if len(parts) >= 2:
                    break
            info["time"] = " ".join(parts).strip()
        if TEAM_HEADER_RE.match(s):
            info["team_headers"].append(s)
    return info


def extract_players(cells):
    """从名单中解析玩家: [{name, qq, jobs, section}]"""
    players = []
    n = len(cells)
    # 定位玩家区域
    start = None
    for i in range(len(cells)):
        s = clean(cells[i]) if isinstance(cells[i], str) else ""
        if s in ("主职", "主职-副职", "ID", "辅助职业", "QQ", "进度"):
            start = i + 1
            break
    if start is None:
        for i in range(len(cells)):
            s = clean(cells[i]) if isinstance(cells[i], str) else ""
            if s in ("A队",) or s.startswith("A队"):
                start = i + 3
                break
        if start is None:
            start = 55

    i = start
    section = "ABC"  # ABC区 / 123区(功能队)
    seen_player = False
    while i < n:
        v = cells[i]
        s = clean(v) if isinstance(v, str) else ""
        # 队名头: 玩家出现后出现的队头标记分区切换
        if re.match(r"^[ABCabc123]\s*队|^[D-Fd-f]队", s):
            if seen_player and re.match(r"^[123DdEeFf]", s):
                section = "123"
            i += 1
            continue
        if is_qq(s):
            if players:
                players[-1]["qq"] = s
            i += 1
            continue
        if not s or TEAM_HEADER_RE.match(s) or s.startswith(("填表", "表上", "每队", "副职黑魔", "本次", "小tips", "老四", "道中", "奶妈看", "必须", "12:", "13:", "11:", "15:", "16:", "提前", "补正", "幻影", "功能位", "抽奖", "群号", "伐木类", "临时", "自行", "车头", "轮数", "时间", "招募大区", "速刷", "1小时", "OOPZ", "陆行鸟", "劳改", "招募密码", "当天", "不是40", "详细", "中奖", "自由位统计")):
            i += 1
            continue
        if is_job_token(s):
            if players:
                for part in re.split(r"[/、,， ]", s):
                    if part:
                        players[-1]["jobs"].append(part)
            i += 1
            continue
        if s.startswith(("位置", "ID", "QQ", "进度", "主职", "辅助职业", "过本次数", "备注")):
            i += 1
            continue
        # 数字索引(1-48): 跳过
        if re.fullmatch(r"[1-9]\d?", s) and 1 <= int(s) <= 60:
            i += 1
            continue
        # 玩家名字
        players.append({"name": s, "jobs": [], "qq": "", "section": section})
        seen_player = True
        i += 1

    # 按分区内位置 mod 3 分配队伍(各区3列: ABC或123)
    sec_count = {}
    for p in players:
        idx = sec_count.get(p["section"], 0)
        p["team"] = p["section"] + str(idx % 3 + 1)
        sec_count[p["section"]] = idx + 1
    out = []
    for p in players:
        if p["name"] and (p["qq"] or p["jobs"]) and len(p["name"]) <= 20:
            out.append(p)
    return out


def team_of(p):
    """队伍(精确): 使用网格解析的队名"""
    return p.get("team", "")


def build_database():
    """扫描所有车表, 建立玩家数据库"""
    session, records = get_records()
    print(f"扫描 {len(records)} 个车表名单...")
    db = []  # [{time, leader, label, doc, tab, players}]
    for r in records:
        try:
            rows = get_grid(r["doc"], r["tab"])
            if rows is None:
                print(f"  - {r['record_id']} 无法访问, 跳过")
                continue
            info = extract_roster_info([])
            players = parse_grid_players(rows)
            db.append({
                "record_id": r["record_id"],
                "doc": r["doc"],
                "tab": r["tab"],
                "time": r["time"] or info["time"],
                "leader": r["leader"] or info["leader"],
                "label": r["label"],
                "players": players,
            })
            print(f"  ✓ {r['record_id']} {db[-1]['time']} {db[-1]['leader']}: {len(players)}人")
        except Exception as e:
            print(f"  - {r['record_id']} 出错: {e}")
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    print(f"数据库已保存: {DB_FILE}")
    return db


def load_database():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def query(db, keyword):
    kw = keyword.strip()
    results = []
    for roster in db:
        for p in roster["players"]:
            if p["qq"] == kw or p["name"] and kw in p["name"]:
                results.append((roster, p))
    return results


def main():
    rebuild = "--rebuild" in sys.argv
    db = build_database() if rebuild or not os.path.exists(DB_FILE) else load_database()
    if db is None:
        db = build_database()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        show_results(db, args[0])
    else:
        print("===== 玩家查询工具 =====")
        print("输入玩家名或QQ查询, 直接回车退出")
        print("(数据库如过期, 先运行: python query_renshu.py --rebuild)")
        while True:
            kw = input("\n请输入名字或QQ: ").strip()
            if not kw:
                break
            show_results(db, kw)


def fmt_jobs(p):
    """主职/副职 格式"""
    main = p.get("main", "")
    sub = p.get("sub", "")
    return f"{main}/{sub}"


def roster_url(roster):
    return f"https://docs.qq.com/sheet/{roster['doc']}?tab={roster['tab']}"


def time_sort_key(time_str):
    """把 '08-15 14:00' 或 '2026/8/10 20:00' 转成可排序元组(月,日,时,分)"""
    s = (time_str or "").strip()
    m = re.match(r"(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m2 = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m2:
        return (int(m2.group(2)), int(m2.group(3)), int(m2.group(4)), int(m2.group(5)))
    return (0, 0, 0, 0)


def is_upcoming(time_str):
    """判断记录时间是否未过期(>= 当前时间)"""
    k = time_sort_key(time_str)
    if k == (0, 0, 0, 0):
        return True  # 无时间的记录保留
    now = time.localtime()
    nowk = (now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min)
    return k >= nowk


def show_results(db, kw):
    results = query(db, kw)
    if not results:
        print(f"未找到 '{kw}' 的报名记录")
        return
    # 只保留未过期的, 按日期正序排列(早的在前)
    results = [r for r in results if is_upcoming(r[0].get("time", ""))]
    results.sort(key=lambda x: time_sort_key(x[0].get("time", "")))
    print(f"\n===== '{kw}' 共找到 {len(results)} 条记录 (按日期正序, 已过期不显示) =====")
    for roster, p in results:
        print(f"  ■ 车表: {roster['label'] or roster['time'] or '?'}  ({roster['time'] or '?'} 车头 {roster['leader'] or '?'})")
        print(f"    玩家: {p['name']}  (QQ {p['qq']})")
        print(f"    位置: {fmt_jobs(p)}")
        print(f"    所在队伍: {team_of(p)}")
        print(f"    名单: {roster_url(roster)}")
        print()


if __name__ == "__main__":
    main()
