#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · famous 繁简漏判修复(名录归一化,成员冻结)
====================================================

背景:batch-001 生成时,《唐诗三百首》名录(tang300)为繁体、未归一化,唐诗类 famous
大量漏判。主编 2026-07-07 授权:对**名录**做繁→简归一化(opencc t2s,仅名录、不转语料
——作废的是「语料繁简转换」,名录归一化另论)。

本脚本**不重跑采收、不重选成员**(famous 是排序键,重跑会改动头部,主编已裁定冻结):
  1. 用归一化后的名录,**就地**重算 batch-001.json 每条候选的 famous / anthology(顺序、成员不动)。
  2. 同步 batch.meta.counts 与 docs/harvest-report.md 的 famous 数字。
  3. 扫 data/harvest.raw.jsonl:找「归一后 famous、且会挤进该辰头部前 20、却不在冻结批次里」的
     **遗珠**,单列 docs/harvest-errata-001.md,供主编决定是否加发 batch-001b。

红线不变:不写 poems.json / candidates.json;source_note 一律「待溯源」;只注不裁,主编终裁。

用法:D:\\conda\\miniconda3\\python.exe scripts/refresh_famous.py
"""

import sys
import os
import re
import json
import heapq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harvest_time_words as H          # 复用 norm_cjk / poem_famous / load_anthologies / get_t2s / SENT_SEP

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = os.path.join(ROOT, "data", "harvest", "batch-001.json")
RAW = os.path.join(ROOT, "data", "harvest.raw.jsonl")
REPORT = os.path.join(ROOT, "docs", "harvest-report.md")
ERRATA = os.path.join(ROOT, "docs", "harvest-errata-001.md")
ANTH = os.path.join(ROOT, "corpus", "anthology")


def title_of(entry):
    return (entry.get("source") or "").strip("《》")


def first_line_of(entry):
    txt = entry.get("full_poem") or entry.get("line") or ""
    return H.clean_sentence(H.SENT_SEP.split(txt)[0])


def refresh_batch(idx):
    """就地重算 batch famous / anthology(冻结成员与顺序)。→ (batch, per_new, up, down)。"""
    batch = json.load(open(BATCH, encoding="utf-8"))
    per = batch["meta"]["counts"]["per_shichen"]
    up = down = 0
    for sc in batch["shichen"]:
        head_famous = 0
        for e in sc["candidates"]:
            fam, anth = H.poem_famous(e.get("author", ""), title_of(e), first_line_of(e), idx)
            old = bool(e.get("famous"))
            if fam and not old:
                up += 1
            if old and not fam:                     # 归一化只增不减;若出现即为异常,报出
                down += 1
                print("  [warn] famous True→False(异常):", e["line"])
            e["famous"] = fam
            e["anthology"] = anth
            if fam:
                head_famous += 1
        per[sc["id"]]["famous"] = head_famous        # 头部 famous(报告表用)
    return batch, per, up, down


def scan_raw(idx, frozen):
    """扫 raw:每辰统计归一后 famous 总数,并求「新排序下头部前 20」以挖遗珠。
    frozen[sid] = 冻结批次的 line 指纹集合。→ (famous_distinct, gems)。"""
    famous_distinct = {}
    heaps = {}                                       # sid → 大小≤20 的最小堆,保留新排序前 20
    n = 0
    with open(RAW, encoding="utf-8") as f:
        for i, ln in enumerate(f):
            ln = ln.strip()
            if not ln:
                continue
            o = json.loads(ln)
            sid = o["shichen"]
            fam, anth = H.poem_famous(o.get("author", ""), title_of(o), first_line_of(o), idx)
            famous_distinct[sid] = famous_distinct.get(sid, 0) + (1 if fam else 0)
            tier1 = 1 if o.get("tier") == 1 else 0
            score = (o.get("harvest") or {}).get("score", 0)
            key = (1 if fam else 0, tier1, score, -i)   # 与采收同序:famous>tier1>score,tie 取先入(i 小)
            rec = (key, {"line": o["line"], "author": o.get("author", ""),
                         "dynasty": o.get("dynasty", ""), "source": o.get("source", ""),
                         "anthology": anth, "famous": fam})
            h = heaps.setdefault(sid, [])
            if len(h) < 20:
                heapq.heappush(h, rec)
            elif key > h[0][0]:
                heapq.heapreplace(h, rec)
            n += 1
    gems = {}
    for sid, h in heaps.items():
        top = sorted(h, key=lambda r: r[0], reverse=True)
        gems[sid] = [rec for _, rec in
                     [(k, v) for k, v in top if H.norm_cjk(v["line"]) not in frozen.get(sid, set())]]
    print("  raw 扫描 %d 条。" % n)
    return famous_distinct, gems


def patch_report(per, order, total_famous):
    """把 harvest-report.md 的 famous 表列与「famous 命中率」段落改为归一后的新数字。"""
    txt = open(REPORT, encoding="utf-8").read()
    lines = txt.split("\n")
    hdr = "| 时辰 | 别名 | 命中(去重前) | 去重后 | 入批头部 | famous |"
    if hdr not in lines:
        sys.exit("!! 报告表头锚点未找到,请手动核对 harvest-report.md。")
    i = lines.index(hdr)
    j = i + 2                                        # 跳过表头 + 分隔线
    k = j
    while k < len(lines) and lines[k].startswith("|"):
        k += 1
    rows = ["| %s | %s | %d | %d | %d | %d |" %
            (per[sid]["name"], per[sid]["alias"], per[sid]["hits"],
             per[sid]["distinct"], per[sid]["head"], per[sid]["famous"]) for sid in order]
    lines = lines[:j] + rows + lines[k:]
    txt = "\n".join(lines)

    block = "## famous 命中率\n\n" + "\n".join([
        "- 头部入批共 240 条,其中 famous(命中《唐诗三百首》/《宋词三百首》名录)%d 条,占 %.1f%%。" %
        (total_famous, 100.0 * total_famous / 240),
        "- 说明:《唐诗三百首》原文繁体,已按主编 2026-07-07 授权对**名录**做繁→简归一化(opencc t2s,"
        "仅名录、不转语料)后与简体语料精确匹配;《宋词三百首》本简体,按「作者+首句」命中。opencc 缺失时回退为召回下限。",
        "- tier(一线名家表,作者名简体匹配,稳定)已作主排序,不受繁简影响。",
        "- 遗珠:归一化前漏判、头部之外另有 famous 遗珠;详见 docs/harvest-errata-001.md,由主编决定是否加发 batch-001b。",
    ])
    if "## famous 命中率" not in txt:
        sys.exit("!! famous 命中率段落锚点未找到。")
    txt = re.sub(r"## famous 命中率\n.*?(?=\n## )", lambda m: block + "\n", txt, count=1, flags=re.S)
    open(REPORT, "w", encoding="utf-8").write(txt)


def write_errata(order, per, famous_distinct, gems, old_total, new_total):
    L = []
    L.append("# 采收遗珠附录 · batch-001-errata\n")
    L.append("> 缘由:《唐诗三百首》名录(tang300)原为繁体,batch-001 生成时未做繁→简归一化,唐诗类 famous 大量漏判。")
    L.append("> 主编 2026-07-07 授权对**名录**做归一化(opencc t2s,仅名录、不转语料)。")
    L.append("> **batch-001 成员已冻结,本附录不改动 batch-001**;仅列「若当初 famous 判对、会挤进该辰头部前 20、")
    L.append("> 却不在冻结批次里」的遗珠,供主编决定是否加发 **batch-001b**。名录归一化只增不减命中,故遗珠皆**应入而未入**。")
    L.append("> 红线不变:遗珠 source_note 仍「待溯源」,晋升前逐句对通行本核字;本附录只列,不裁。")
    L.append(">")
    L.append("> ⚠ 排序口径:遗珠仅按 `famous + tier + 句形分` 排序,**未经 §2-D 语义标注**,多义时间词的噪声原样带入。")
    L.append("> 尤以**辰时「朝」**为最——朝代 / 朝廷 / 朝觐 / 朝向 / 明朝=来晨(如「汉朝公卿」「圣朝无阙事」「奔凑似朝东」),")
    L.append("> 与头部 13 条 drop 同源;卯时亦有「读难晓=知晓」之属。故辰时 20 条全数换血系「朝」名句涌入排序所致,")
    L.append("> **非**净增 20 首晨景实指。主编若据此出 batch-001b,须对遗珠重跑语义标注 + 核字后再定去留。\n")

    tot_gem = sum(len(gems.get(sid, [])) for sid in order)
    L.append("## 概览\n")
    L.append("- 头部 famous:归一前 **%d** → 归一后 **%d**(冻结成员就地重判,未换人)。" % (old_total, new_total))
    L.append("- 遗珠合计 **%d** 条(会挤进各辰前 20 却不在冻结批次里)。晋升须主编另发 batch-001b。\n" % tot_gem)
    L.append("| 时辰 | 别名 | 去重命中 | famous(归一后) | 头部 famous | 遗珠(应挤进前20) |")
    L.append("|---|---|---:|---:|---:|---:|")
    for sid in order:
        L.append("| %s | %s | %d | %d | %d | %d |" %
                 (per[sid]["name"], per[sid]["alias"], per[sid]["distinct"],
                  famous_distinct.get(sid, 0), per[sid]["famous"], len(gems.get(sid, []))))

    L.append("\n## 各时辰遗珠明细(归一后 famous、应挤进前 20 而未入)\n")
    any_gem = False
    for sid in order:
        g = gems.get(sid, [])
        if not g:
            continue
        any_gem = True
        L.append("### %s·%s(遗珠 %d)\n" % (per[sid]["name"], per[sid]["alias"], len(g)))
        L.append("| 句 | 作者 | 朝代 | 名录 | 题 |")
        L.append("|---|---|---|---|---|")
        for r in g:
            anth = r["anthology"] or ("★" if r["famous"] else "")
            L.append("| %s | %s | %s | %s | %s |" %
                     (r["line"], r["author"] or "佚名", r["dynasty"] or "", anth, title_of(r)))
        L.append("")
    if not any_gem:
        L.append("- (无遗珠:归一化未使任何头部之外的 famous 挤进前 20。)")
    open(ERRATA, "w", encoding="utf-8").write("\n".join(L))


def main():
    t2s = H.get_t2s()
    idx = H.load_anthologies(ANTH, t2s)
    print("名录条目(归一后):%d %s" % (len(idx), "(opencc 已启用)" if t2s else "(opencc 缺失,未归一)"))

    old = json.load(open(BATCH, encoding="utf-8"))
    old_total = sum(1 for sc in old["shichen"] for e in sc["candidates"] if e.get("famous"))
    order = list(old["meta"]["counts"]["per_shichen"].keys())
    frozen = {sc["id"]: set(H.norm_cjk(e["line"]) for e in sc["candidates"]) for sc in old["shichen"]}

    batch, per, up, down = refresh_batch(idx)
    new_total = sum(v["famous"] for v in per.values())

    famous_distinct, gems = scan_raw(idx, frozen)
    for sid in order:                                # 同步 famous_distinct 到 meta
        per[sid]["famous_distinct"] = famous_distinct.get(sid, 0)

    batch["meta"]["counts"]["famous_head_total"] = new_total
    batch["meta"]["famous_refresh"] = {
        "date": "2026-07-07",
        "method": "名录 tang300 繁→简归一化(opencc t2s,仅名录、不转语料);成员冻结,只重判 famous 字段。",
        "head_famous_before": old_total, "head_famous_after": new_total,
        "errata": "docs/harvest-errata-001.md(头部之外遗珠,供主编决定是否出 batch-001b)",
    }
    json.dump(batch, open(BATCH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    patch_report(per, order, new_total)
    write_errata(order, per, famous_distinct, gems, old_total, new_total)

    print("头部 famous:%d → %d(新增 %d;异常回落 %d)。" % (old_total, new_total, up, down))
    print("各辰头部 famous(归一后):")
    for sid in order:
        print("  %-5s %s head_famous=%-3d famous_distinct=%-5d 遗珠=%d"
              % (sid, per[sid]["name"], per[sid]["famous"], per[sid]["famous_distinct"], len(gems.get(sid, []))))
    print("遗珠合计 %d 条 → %s" % (sum(len(v) for v in gems.values()), os.path.basename(ERRATA)))
    print("已就地更新 %s,并同步 %s。" % (os.path.basename(BATCH), os.path.basename(REPORT)))


if __name__ == "__main__":
    main()
