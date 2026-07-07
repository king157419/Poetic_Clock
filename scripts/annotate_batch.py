#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 采收批次语义标注(§2-D:实指时刻 keep / drop + 理由)
================================================================

对 data/harvest/batch-001.json 头部候选**逐条**判断:该 time_word 在此句中是否
**实指时刻**(排除人名 / 地名 / 虚指 / 典故借用 / 断读误命中)。

铁律:**只注不裁**。drop 的条目仍留在批次里、附理由,主编可推翻;keep/drop 皆非最终裁决。
本文件是采收人(逐条人工过的)判断记录,可版本化复现;主编终裁。

用法:python scripts/annotate_batch.py   # 就地写回 batch,并把标注结果并入 harvest-report.md
"""

import sys
import os
import re
import json

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH = os.path.join(ROOT, "data", "harvest", "batch-001.json")
REPORT = os.path.join(ROOT, "docs", "harvest-report.md")
CJK = re.compile(r"[一-鿿]")
MARK = "## 人工语义标注(§2-D)"


def norm(s):
    return "".join(CJK.findall(s or ""))


# ── drop:time_word 非实指时刻。键 = (时辰id, 句子汉字指纹, time_word) ──
# 只列 drop 与需加注的 keep;其余一律 keep(理由按 time_word 模板生成)。
DROPS = [
    # 辰时「朝」高噪:朝代 / 虚指 / 动词『朝觐』/ 典故,均非晨朝
    ("chen", "明朝有封事，数问夜如何", "「明朝」指来晨,且诗中此刻为夜(数问夜如何),非当下辰时"),
    ("chen", "扁舟空老去，无补圣明朝", "「圣明朝」指圣明朝廷 / 治世,非晨朝"),
    ("chen", "唯将迟暮供多病，未有涓埃荅圣朝", "「圣朝」指朝廷,非晨朝"),
    ("chen", "三顾频烦天下计，两朝开济老臣心", "「两朝」指两代朝廷,非晨朝"),
    ("chen", "折戟沈沙铁未销，自将磨洗认前朝", "「前朝」指前代王朝,非晨朝"),
    ("chen", "明朝车马各西东，惆怅画桥风与月", "「明朝」指来日,虚指未来非当下辰时"),
    ("chen", "主人朝玉京", "「朝玉京」朝为『朝觐 / 趋向』动词,非晨朝"),
    ("chen", "今朝放罪上恩宽", "「今朝」犹『今日 / 如今』,虚指非晨"),
    ("chen", "南朝盛事谁记", "「南朝」指朝代,非晨朝"),
    ("chen", "六朝旧事如流水，但寒烟、衰草凝绿", "「六朝」指朝代,非晨朝"),
    ("chen", "征衫，便好去朝天", "「朝天」朝觐天子,朝为动词非晨"),
    ("chen", "好时代、朝野多欢，遍九陌、太平箫鼓", "「朝野」朝廷与民间,非晨朝"),
    ("chen", "醉里秋波，梦中朝雨，都是醒时烦恼", "「朝雨」用巫山朝云暮雨典,喻欢会非实晨"),
    # 断读误命中(time_word 跨词边界拼出)
    ("you", "明日落红应满径", "「日落」实为『明日·落红』断读,非日落"),
    ("chou", "桑叶下墟落，鹍鸡鸣渚田", "「鸡鸣」实为『鹍鸡·鸣』断读,非报晓之鸡鸣"),
    # 虚指 / 借义
    ("mao", "无为大道人难晓", "「难晓」晓为『知晓 / 明白』,非拂晓"),
    ("xu", "唯将迟暮供多病，未有涓埃荅圣朝", "「迟暮」喻晚年,非黄昏"),
]

# ── keep 但需加注(泛指 / 借景 / 纠正 auto 误报),覆盖默认理由 ──
KEEP_NOTES = [
    ("chen", "帝里风光好，当年少日，暮宴朝欢", "「朝欢」与『暮宴』对举,泛咏朝暮,姑存(朝指晨)"),
    ("chen", "叙旧期、不负春盟，红朝翠暮", "「红朝翠暮」朝暮对举,泛指,姑存"),
    ("chen", "岁岁金河复玉关，朝朝马策与刀环", "「朝朝」日日之晨,实指晨(戍边朝暮)"),
    ("xu", "暮云空阔不知音，惟有绿杨芳草路", "「暮云」薄暮之云,实指黄昏(auto suspect 系误报)"),
]


def main():
    drop_idx = {}
    for sid, line, why in DROPS:
        drop_idx[(sid, norm(line))] = why       # 简化:同一(辰,句)只一条判定
    keep_idx = {(sid, norm(line)): why for sid, line, why in KEEP_NOTES}

    d = json.load(open(BATCH, encoding="utf-8"))
    n_keep = n_drop = 0
    per_drop = {}
    drop_rows = []
    for sc in d["shichen"]:
        alias = sc["alias"]
        for e in sc["candidates"]:
            k = (sc["id"], norm(e["line"]))
            tw = e["time_word"]
            if k in drop_idx:
                e["semantic"] = {"verdict": "drop", "reason": drop_idx[k], "by": "harvest-annotator"}
                n_drop += 1
                per_drop[sc["name"]] = per_drop.get(sc["name"], 0) + 1
                drop_rows.append((sc["name"], tw, e["line"], drop_idx[k]))
            elif k in keep_idx:
                e["semantic"] = {"verdict": "keep", "reason": keep_idx[k], "by": "harvest-annotator"}
                n_keep += 1
            else:
                e["semantic"] = {"verdict": "keep",
                                 "reason": "「%s」直书%s此刻,实指时刻" % (tw, alias),
                                 "by": "harvest-annotator"}
                n_keep += 1

    # 元信息记录标注已完成
    d["meta"]["semantic_done"] = True
    d["meta"]["semantic_summary"] = {"keep": n_keep, "drop": n_drop, "per_shichen_drop": per_drop}
    json.dump(d, open(BATCH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 并入报告(幂等:截到 MARK 之前再追加)
    body = ""
    if os.path.exists(REPORT):
        body = open(REPORT, encoding="utf-8").read()
        i = body.find(MARK)
        if i != -1:
            body = body[:i].rstrip() + "\n"
    L = [body.rstrip(), "", MARK, ""]
    L.append("采收人逐条判断 time_word 是否**实指时刻**(排除人名 / 地名 / 虚指 / 典故 / 断读误命中)。"
             "**只注不裁**,drop 仍留批次附理由,主编终裁。\n")
    L.append("- 头部 240 条:**keep %d / drop %d**(drop 率 %.1f%%)。" %
             (n_keep, n_drop, 100.0 * n_drop / (n_keep + n_drop)))
    if per_drop:
        L.append("- 各时辰 drop 数:" + "、".join("%s %d" % (k, v) for k, v in per_drop.items()) + "。")
    L.append("- 主要噪声源:**辰时「朝」**——朝代(南朝 / 六朝 / 前朝 / 两朝 / 圣朝)、虚指(今朝 / 明朝)、"
             "动词朝觐(朝天 / 朝玉京)大量占位,20 条头部约三分之二非实指晨时;单字多义词是数据检索的主要误命中来源。\n")
    L.append("### drop 明细(供主编复核,可推翻)\n")
    L.append("| 时辰 | 词 | 句 | 理由 |")
    L.append("|---|---|---|---|")
    for name, tw, line, why in drop_rows:
        L.append("| %s | %s | %s | %s |" % (name, tw, line, why))
    L.append("")
    open(REPORT, "w", encoding="utf-8").write("\n".join(L))

    print("标注完成:keep %d / drop %d(共 %d)。各辰 drop:%s" %
          (n_keep, n_drop, n_keep + n_drop, per_drop))
    print("已写回 %s 并并入 %s" % (os.path.basename(BATCH), os.path.basename(REPORT)))


if __name__ == "__main__":
    main()
