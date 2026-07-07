#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 采收批次审读表生成(主编审读界面)
==============================================

把 data/harvest/batch-001.json 渲染成 docs/review-001.md:
  · 按十二时辰分组;**组内 keep,famous 在前**(famous → tier1 → 批次原序)。
  · 每条一行:编号 / 句 / 出处 / famous / tier / 语义注。
  · 17 条 drop 不散在各组,**集中列于末尾**并附理由。

只读渲染:不改 batch,不裁诗句。红线——所有条目 source_note 一律「待溯源」,
「出处」列仅为**待核**的作者 / 篇题线索,晋升前须主编逐句对通行本核字。

用法:D:\\conda\\miniconda3\\python.exe scripts/make_review.py
"""

import sys
import os
import json

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = os.path.join(ROOT, "data", "harvest", "batch-001.json")
OUT = os.path.join(ROOT, "docs", "review-001.md")

ANTH_SHORT = {"唐诗三百首": "唐诗", "宋词三百首": "宋词"}


def prov(e):
    """待核出处线索:〔朝代〕作者《篇题》。篇题过长(词多带词序)时截断,全称仍存 batch 供核字。"""
    dyn = ("〔%s〕" % e["dynasty"]) if e.get("dynasty") else ""
    title = (e.get("source") or "").strip("《》")
    if len(title) > 18:
        title = title[:18] + "…"
    src = ("《%s》" % title) if title else ""
    return "%s%s%s" % (dyn, e.get("author") or "佚名", src)


def famcell(e):
    if e.get("famous"):
        return ANTH_SHORT.get(e.get("anthology") or "", "★")
    return "—"


def semnote(e):
    s = e.get("semantic") or {}
    note = (s.get("reason") or "").strip()
    if (e.get("harvest") or {}).get("auto_hint") == "suspect" and s.get("verdict") == "keep":
        note = "⚠ " + note        # keep 但 auto 判 suspect:请主编重点复核
    return note or "—"


def esc(s):
    return (s or "").replace("|", "\\|")


def main():
    d = json.load(open(BATCH, encoding="utf-8"))
    keeps = {}     # sid → [entry...]
    drops = []     # (sid, name, entry)
    meta = d["meta"]["counts"]["per_shichen"]
    for sc in d["shichen"]:
        ks = []
        for e in sc["candidates"]:
            v = (e.get("semantic") or {}).get("verdict")
            if v == "drop":
                drops.append((sc["id"], sc["name"], e))
            else:
                ks.append(e)
        # 组内:famous 在前 → tier1 在前 → 批次原序(稳定)
        ks_i = list(enumerate(ks))
        ks_i.sort(key=lambda p: (0 if p[1].get("famous") else 1,
                                 0 if p[1].get("tier") == 1 else 1, p[0]))
        keeps[sc["id"]] = [e for _, e in ks_i]

    n_keep = sum(len(v) for v in keeps.values())
    n_drop = len(drops)
    n_fam = sum(1 for v in keeps.values() for e in v if e.get("famous"))

    L = []
    L.append("# 采收审读表 · review-001\n")
    L.append("> 主编审读界面。源:`data/harvest/batch-001.json`(闸门后待审,**未入正库**)。")
    L.append("> 共 %d 条:keep %d / drop %d;keep 中 famous %d。按时辰分组,组内 famous 在前;drop 集中于末尾。\n"
             % (n_keep + n_drop, n_keep, n_drop, n_fam))
    L.append("**红线**:全部 `source_note=待溯源`。下表「出处」列仅为**待核**的作者 / 篇题线索(源自 Werneror 检索,"
             "非权威出处);晋升前须逐句对通行本 / 权威选本核字、补真实卷次。本表只供审读,不代表已核准。")
    L.append("**用法**:逐条判 收 / 弃 / 存疑;`famous` 列 唐诗 / 宋词 = 命中名录,— = 未命中(不等于不好);"
             "`tier` T1=一线名家;`语义注` 前带 ⚠ = 采收判 keep 但 auto 疑虑,请重点核。")
    L.append("**遗珠**:名录归一化后头部之外的 famous 遗珠见 `docs/harvest-errata-001.md`(是否加发 batch-001b 由主编定)。\n")

    L.append("---\n")
    for sc in d["shichen"]:
        sid = sc["id"]
        rows = keeps[sid]
        fam_n = sum(1 for e in rows if e.get("famous"))
        L.append("## %s·%s(keep %d,其中 famous %d)\n" % (sc["name"], sc["alias"], len(rows), fam_n))
        L.append("| 编号 | 句 | 出处(待核) | famous | tier | 语义注 |")
        L.append("|---|---|---|:--:|:--:|---|")
        for i, e in enumerate(rows, 1):
            L.append("| %s-%02d | %s | %s | %s | %s | %s |" % (
                sc["name"][0], i, esc(e["line"]), esc(prov(e)), famcell(e),
                "T1" if e.get("tier") == 1 else "T2", esc(semnote(e))))
        L.append("")

    L.append("---\n")
    L.append("## drop 明细(采收判非实指时刻;只注不裁,主编可推翻)\n")
    L.append("| 编号 | 时辰 | 词 | 句 | 出处(待核) | 理由 |")
    L.append("|---|---|:--:|---|---|---|")
    for j, (sid, name, e) in enumerate(drops, 1):
        L.append("| drop-%02d | %s | %s | %s | %s | %s |" % (
            j, name, e["time_word"], esc(e["line"]), esc(prov(e)),
            esc((e.get("semantic") or {}).get("reason") or "")))
    L.append("")

    open(OUT, "w", encoding="utf-8").write("\n".join(L))
    print("已生成 %s:keep %d(famous %d)/ drop %d。" % (os.path.basename(OUT), n_keep, n_fam, n_drop))


if __name__ == "__main__":
    main()
