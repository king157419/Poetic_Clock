#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 语料下载器(时间词采收管线 第 0 步)
================================================

把 Werneror/Poetry(约 85 万首古诗词,按朝代分片的 CSV)下载到本地 corpus/ 目录,
供 scripts/harvest_time_words.py 检索。**只下载,不检索;语料不入库**(corpus/ 已在 .gitignore)。

铁律与定位:
    Werneror 语料库是**检索工具**,不是出处。采收出的句子在晋升前,出处一律「待溯源」,
    须由主编逐句对通行本 / 权威选本(《全唐诗》卷次等)核字后方可入库。

用法:
    D:\\conda\\miniconda3\\python.exe scripts/fetch_corpus.py            # 下载全部朝代 CSV
    python scripts/fetch_corpus.py --only 唐 宋 先秦 魏晋 南北朝 隋      # 只下载指定朝代(名句密度高)
    python scripts/fetch_corpus.py --list                              # 只列文件清单,不下载
    python scripts/fetch_corpus.py --dest D:\\some\\dir                  # 自定义落盘目录

数据源:https://github.com/Werneror/Poetry (LICENSE 见其仓库)。列:题目,朝代,作者,内容(UTF-8)。
断点续传:已存在且大小与远端一致的文件跳过;不一致则重下。
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.parse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEST = os.path.join(ROOT, "corpus", "werneror")
API = "https://api.github.com/repos/Werneror/Poetry/contents/"
RAW = "https://raw.githubusercontent.com/Werneror/Poetry/master/"
UA = {"User-Agent": "poetric-clock-harvest/1.0 (+https://github.com/Werneror/Poetry)"}


def http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def list_csvs():
    """返回 [(name, size), ...],仅 .csv,按 size 升序(小库先下,快速见到进度)。"""
    items = http_json(API)
    csvs = [(it["name"], it["size"]) for it in items
            if it["type"] == "file" and it["name"].endswith(".csv")]
    csvs.sort(key=lambda x: x[1])
    return csvs


def download(name, size, dest_dir):
    dst = os.path.join(dest_dir, name)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        print("  跳过(已存在): %s (%.1f MB)" % (name, size / 1e6))
        return "skip"
    url = RAW + urllib.parse.quote(name)
    tmp = dst + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
    os.replace(tmp, dst)
    print("  下载完成: %s (%.1f MB)" % (name, done / 1e6))
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="下载 Werneror/Poetry 语料到本地 corpus/")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="落盘目录(默认 corpus/werneror)")
    ap.add_argument("--only", nargs="*", default=None,
                    help="只下载文件名含这些子串的朝代(如 唐 宋 先秦)")
    ap.add_argument("--list", action="store_true", help="只列清单,不下载")
    args = ap.parse_args()

    csvs = list_csvs()
    if args.only:
        csvs = [(n, s) for (n, s) in csvs if any(k in n for k in args.only)]

    total = sum(s for _, s in csvs)
    print("清单:%d 个 CSV,合计 %.1f MB" % (len(csvs), total / 1e6))
    for n, s in csvs:
        print("  - %-24s %8.1f MB" % (n, s / 1e6))
    if args.list:
        return

    os.makedirs(args.dest, exist_ok=True)
    ok = skip = 0
    for i, (n, s) in enumerate(csvs, 1):
        print("[%d/%d] %s" % (i, len(csvs), n))
        try:
            r = download(n, s, args.dest)
            ok += (r == "ok")
            skip += (r == "skip")
        except Exception as e:
            print("  !! 失败:%s —— %s" % (n, e))

    manifest = {
        "source": "https://github.com/Werneror/Poetry",
        "note": "检索工具,非出处;采收句晋升前须逐句对通行本核字。",
        "columns": ["题目", "朝代", "作者", "内容"],
        "files": [{"name": n, "size": s} for n, s in csvs],
    }
    with open(os.path.join(args.dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("完成:新下载 %d,跳过 %d,落盘 %s" % (ok, skip, args.dest))


if __name__ == "__main__":
    main()
