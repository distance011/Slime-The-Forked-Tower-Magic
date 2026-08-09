#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
史莱姆团发车表 - 人数自动统计更新脚本
每隔5分钟：读取各「车表」名单 -> 统计填写QQ的人数 -> 自动更新发车表的「人数」列
用法: python update_renshu.py
"""

import json
import re
import time
import uuid
import random
import base64
import gzip
import zlib
import urllib.request
import urllib.parse
import socket
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ================= 配置(从 config.py 导入, 勿提交) =================
try:
    from config import (UID, UID_KEY, TOK, COOKIE, DOC_URL, UPID, PADID,
                        DOCID, SUBID, TABLEID, GENERALPACKET, AVATAR)
except ImportError:
    print("缺少 config.py！请复制 config.example.py 为 config.py 并填写配置。")
    raise

REFRESH_INTERVAL = 300   # 每5分钟更新一次

QQ_RE = re.compile(r"^\d{6,11}$")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 无法访问的名单文档（需登录等），跳过不统计
SKIP_DOCS = {"DUUVEQVNsaWtvS3dS"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- 读取发车表 + 会话 ----------
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
    """读取发车表，返回 [{record_id, doc, tab, current}]"""
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
        # 车表链接 f4vckj (type 8): k8 list of {k2:text, k3:url}
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
        # 车表名称 (f4vckj k2 text)
        label = ""
        if v and "k8" in v:
            for o in v["k8"]:
                if isinstance(o, dict) and o.get("k2"):
                    label = o["k2"]
                    break
        # 发车时间 fkfKit (datetime, epoch ms)
        dep_time = ""
        tv = fields.get("fkfKit")
        if tv and "k4" in tv:
            ts = tv["k4"]
            try:
                dep_time = time.strftime("%m-%d %H:%M", time.localtime(int(ts) / 1000))
            except Exception:
                pass
        # 当前人数 fgx4Iv (type 1)
        cur = ""
        c = fields.get("fgx4Iv")
        if c and "k1" in c and isinstance(c["k1"], list) and c["k1"]:
            cur = c["k1"][0].get("k2", "")
        # 车头 fHSMJO (type 1)
        leader = ""
        hv = fields.get("fHSMJO")
        if hv and "k1" in hv and isinstance(hv["k1"], list) and hv["k1"]:
            leader = hv["k1"][0].get("k2", "")
        records.append({"record_id": rid, "doc": doc, "tab": tab, "current": cur,
                        "time": dep_time, "label": label, "leader": leader})
    return session, records


# ---------- 读取名单统计人数 ----------
def fetch_roster_cells(doc, tab):
    """从分表SSR页面提取文本数组，失败返回None"""
    url = f"https://docs.qq.com/sheet/{doc}?tab={tab}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={**HEADERS, "Cookie": COOKIE})
            html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
            start = html.find("%5B%22")
            if start < 0:
                time.sleep(1.2)
                continue
            end = html.find("%22%5D", start)
            if end < 0:
                time.sleep(1.2)
                continue
            dec = urllib.parse.unquote(html[start:end + 6])
            return json.loads(dec)
        except Exception as e:
            log(f"  抓取分表失败 {doc}/{tab}: {e}")
            time.sleep(1.5)
    return None


def count_qq(cells):
    if not cells:
        return 0
    return len([v for v in cells if isinstance(v, str) and QQ_RE.match(v.strip())])


# ---------- WebSocket 写入 ----------
def connect_ws(session):
    ws_url = (f"wss://docs.qq.com/websocket/?tag={PADID}&gtag={urllib.parse.quote(DOCID)}"
              f"&utag={UPID}&sig={session['sig']}&uid={UID}&uid_key={urllib.parse.quote(UID_KEY)}"
              f"&u=undefined&padid={PADID}&wo_third_fileid=&EIO=3&transport=websocket")
    import websocket as wslib
    ws = wslib.create_connection(ws_url, timeout=20,
                                 header={"Cookie": COOKIE, **HEADERS})
    ws.settimeout(4)
    ws.recv()  # engine.io open
    # login
    payload = {
        "roomType": "padpage", "roomName": f"padpage/{DOCID}", "upid": UPID,
        "gid": DOCID, "sid": session["sid"], "tid": session["tid"], "sig": session["sig"],
        "data": {"stats": {"screen": ""}},
    }
    head = {
        "apid": session["apid"], "type": "CLIENT_READY",
        "task_id": random.randint(10**15, 10**16 - 1),
        "docid": DOCID, "uid": UID, "cookie": COOKIE, "base_rev": session["rev"],
        "code_ver": 0, "session_type": 0, "gray": 0, "dver": "3.0.0", "wl": "",
        "generalpacket": GENERALPACKET, "docs_type": "smartsheet",
    }
    post = json.dumps(head, ensure_ascii=False, separators=(",", ":")) + "\n" + \
           json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    ws.send("42" + json.dumps(["post", post], ensure_ascii=False))
    for _ in range(6):
        m = ws.recv()
        if "CLIENT_READY" in m:
            return ws
    raise RuntimeError("login timeout")


def commit_count(ws, session, record_id, count, base_rev):
    task_id = random.randint(10**15, 10**16 - 1)
    content = {
        "1": TABLEID, "3": record_id,
        "4": {"fgx4Iv": {"1": [{"1": "text", "2": str(count), "4": {}}], "30": 1, "31": UID}},
        "5": {"1": UID, "2": "。。", "3": AVATAR, "5": 0, "6": "", "8": 0},
        "6": False, "7": False,
    }
    mutation = {"t": 3013, "v": 5, "c": content, "r": random.randint(1, 10**6), "o": 0}
    changeset = json.dumps([[mutation]], ensure_ascii=False, separators=(",", ":"))
    body = json.dumps({
        "baseRev": base_rev, "changeSetCount": 1, "changeset": changeset,
        "apool": "", "keydata": False, "head": False, "subId": SUBID,
        "oSubId": False, "taskId": task_id, "offlineMsg": False,
        "msgInfo": {"pauseMsg": False}, "isWorkbook": False, "notCrossSheet": True,
        "changesetType": "smartsheet", "type": "USER_CHANGES",
        "uuId": f"p.{UID}", "not_cross_sheet": True, "pver": 0,
    }, ensure_ascii=False, separators=(",", ":"))
    head2 = {
        "apid": session["apid"], "type": "USER_CHANGES", "task_id": task_id,
        "docid": DOCID, "uid": UID, "cookie": COOKIE, "base_rev": base_rev,
        "code_ver": 0, "session_type": 0, "gray": 0, "dver": "3.0.0", "wl": "",
        "generalpacket": GENERALPACKET, "docs_type": "smartsheet",
    }
    post = json.dumps(head2, ensure_ascii=False, separators=(",", ":")) + "\n" + body
    ws.send("42" + json.dumps(["post", post], ensure_ascii=False))
    end = time.time() + 15
    while time.time() < end:
        try:
            m = ws.recv()
            if "ACCEPT_COMMIT" in m:
                mr = re.search(r'"new_rev"\s*:\s*(\d+)', m)
                return int(mr.group(1)) if mr else base_rev
            if "COMMIT_ERROR" in m:
                mr = re.search(r'"reason"\s*:\s*"?(\d+)"?', m)
                raise RuntimeError(f"commit error reason={mr.group(1) if mr else '?'}")
            if m == "2":
                ws.send("3")
        except RuntimeError:
            raise
        except Exception:
            return base_rev
    raise RuntimeError("commit timeout")


# ---------- 一次完整更新 ----------
def update_cycle():
    try:
        session, records = get_records()
    except Exception as e:
        log(f"读取发车表失败: {e}")
        return
    log(f"共 {len(records)} 条发车记录, 当前rev={session['rev']}")

    changed = []
    for r in records:
        if r["doc"] in SKIP_DOCS:
            log(f"  - {r['record_id']} ({r['doc']}) 名单文档无法访问, 跳过")
            continue
        try:
            cells = fetch_roster_cells(r["doc"], r["tab"])
            if cells is None:
                log(f"  - {r['record_id']} ({r['doc']}) 名单无法访问, 跳过")
                continue
            n = count_qq(cells)
            r["count"] = n
            if str(n) != r["current"]:
                changed.append(r)
        except Exception as e:
            log(f"  - {r['record_id']} 统计异常: {e}")

    if not changed:
        log("  人数无变化, 无需更新")
        return

    log(f"有 {len(changed)} 条记录人数变化, 开始更新...")
    ws = connect_ws(session)
    base_rev = session["rev"]
    ok = 0
    try:
        for r in changed:
            try:
                base_rev = commit_count(ws, session, r["record_id"], r["count"], base_rev)
                log(f"  ✓ {r['record_id']} 人数 {r['current']} -> {r['count']} (rev {base_rev})")
                ok += 1
            except Exception as e:
                log(f"  ✗ {r['record_id']} 更新失败: {e}")
            time.sleep(0.3)
    finally:
        ws.close()
    log(f"更新完成: {ok}/{len(changed)}")


def main():
    log("===== 人数自动更新脚本启动 =====")
    log(f"每 {REFRESH_INTERVAL} 秒更新一次, Ctrl+C 停止")
    while True:
        try:
            update_cycle()
        except Exception as e:
            log(f"更新出错: {e}")
        time.sleep(REFRESH_INTERVAL)


if __name__ == "__main__":
    main()
