#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 时间词采收管线(检索 + 去重 + 打分 + 知名度先验)
================================================================

从本地语料(Werneror/Poetry,scripts/fetch_corpus.py 下载到 corpus/werneror/)中,
检索**字面上写着某个合法时间词**的诗句,按十二时辰归类,产出**闸门后的待审批次**
data/harvest/batch-001.json,供主编逐条核对后手动晋升。

铁律(与项目一致,不可动摇):
  · 只**检索、逐字提取**真实语料,绝不杜撰 / 拼接 / 改写。
  · Werneror 是**检索工具,不是出处**;harvested 条目 source_note 一律「待溯源」,
    出处须由主编对通行本 / 权威选本(《全唐诗》卷次等)逐句核字后补齐,方可晋升。
  · 不写 poems.json、不直接写 candidates.json;本脚本只产 harvest 批次(待审)。
  · 严禁向批次掺入任何非语料检索所得的句子。

匹配与归属:
  · time_word 必是 line 子串,且必属该时辰在 data/time_words.json 的合法词表(词→时辰唯一)。
  · 正则按词长降序,句内**最长匹配优先**(「日暮」不会被误拆成「暮」)。
  · time_word 只在**正文(内容)**里找;出现在题目而非正文的不算命中(本脚本不扫题目)。

知名度先验(不问模型,只用数据,仅决定排序,非裁决):
  · tier:作者在一线名家表内 → 1,其余 → 2(表见 TIER1,可微调,记 DECISIONS)。
  · famous:该诗命中《唐诗三百首》/《宋词三百首》名录 → true,并记 anthology。
      名录取自 chinese-poetry 仓库(仅这两个文件,不下载其全库),放 corpus/anthology/。
      注:《唐诗三百首》原文为**繁体**;主编 2026-07-07 授权对**名录**做繁→简归一化
      (opencc t2s,仅施于名录 tang300,不转换语料——作废的是语料转换,名录归一化另论),
      归一后与简体语料精确匹配。《宋词三百首》本为简体,按「作者+首句」直接命中。
      opencc 不可用时自动回退为不归一(唐诗类 famous 退化为召回下限)。famous 命中率见报告。
  · 排序:famous > tier1 > tier2 > 句形/时代/词性综合分。

配额:每时辰按排序取前 --per-shichen(默认 20)条,总量 ≤ 240,宁缺毋滥。
全量不丢:所有**去重后**命中写入 --raw(data/harvest.raw.jsonl,已 gitignore),
batch 只是其中每辰头部;稀缺时辰可回 raw 里继续淘。

语义标注(④,人工):batch[].semantic.verdict 由主编 / 采收人逐条判断
「time_word 是否实指时刻」(排除人名 / 地名 / 虚指 / 典故),keep/drop + 理由。
本脚本只给 auto_hint(suspect/likely)作参考,**只注不裁,主编终裁**。

用法:
    D:\\conda\\miniconda3\\python.exe scripts/harvest_time_words.py            # 全量(默认高价值朝代)
    python scripts/harvest_time_words.py --only 先秦 汉 魏晋 南北朝 隋 唐 宋 元  # 指定朝代
    python scripts/harvest_time_words.py --selftest                          # 只跑纯函数自检
    python scripts/harvest_time_words.py --limit 20000                       # 每文件仅扫前 N 行(调试)
"""

import sys
import os
import re
import csv
import json
import glob
import heapq
import argparse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

csv.field_size_limit(1 << 24)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# 默认第一批朝代范围(高名句密度;明 / 清 / 近现代 / 当代量大质杂,本批跳过,记 DECISIONS)
DEFAULT_ERAS = ["先秦", "汉", "魏晋", "南北朝", "隋", "唐", "宋", "元"]

# 句 / 短句切分标点
SENT_SEP = re.compile(r"[。！？!?；;]")          # 词曲的分号也作分句(避免拼出超长 line)
CLAUSE_SEP = re.compile(r"[，,、]")
CJK = re.compile(r"[一-鿿]")             # 只保留汉字用于去重 / 匹配指纹
PUNCT_FULL = {",": "，", ":": "：", "、": "、"}     # 半角→全角(逗号已在句内保留)

# 一线名家表(简体;语料亦简体,作者名匹配稳定)。可微调,微调须记 DECISIONS。
TIER1 = {
    "李白", "杜甫", "白居易", "王维", "孟浩然", "李商隐", "杜牧", "刘禹锡", "柳宗元",
    "王昌龄", "岑参", "韩愈", "温庭筠", "李煜", "苏轼", "辛弃疾", "李清照", "欧阳修",
    "柳永", "秦观", "周邦彦", "陆游", "杨万里", "范成大", "晏殊", "晏几道", "姜夔",
    "王安石", "黄庭坚", "陶渊明",
}

# 单字 / 多义高噪词的上下文反例(命中则 auto_hint=suspect,提示可能非实指时刻)
RISK_CONTEXT = {
    "朝": ["朝廷", "朝野", "朝堂", "王朝", "今朝", "明朝", "一朝", "六朝", "南朝", "北朝",
          "前朝", "本朝", "汉朝", "唐朝", "宋朝", "入朝", "归朝", "朝天", "朝回", "朝罢",
          "朝臣", "朝会", "朝拜", "朝纲", "朝政", "朝市", "天朝", "朝夕", "朝野", "朝章"],
    "晓": ["知晓", "分晓", "不晓", "晓得", "晓事", "通晓", "晓畅", "谁晓", "争晓", "晓谕"],
    "暮": ["暮年", "暮春", "暮秋", "暮齿", "岁暮", "迟暮", "暮景残", "暮云"],
    "晨": ["晨昏", "晨炊", "晨兴"],
}


# ───────────────────────── 载入 ─────────────────────────
def load_time_words():
    """→ (word_info: 词→{shichen...}, shichen_meta: 有序 [(id,name,alias)])"""
    tw = json.load(open(os.path.join(DATA, "time_words.json"), encoding="utf-8"))
    word_info, meta = {}, []
    for sc in tw["shichen"]:
        meta.append((sc["id"], sc["name"], sc["alias"]))
        for w in sc["words"]:
            word_info[w["word"]] = {
                "shichen": sc["id"], "name": sc["name"], "alias": sc["alias"],
                "boundary": bool(w.get("boundary")), "note": w.get("note", ""),
            }
    return word_info, meta


def load_existing_norms():
    """poems.json + candidates.json(含 archived_imagery)已有诗句的去重指纹集合。"""
    norms = set()
    for fn in ("poems.json", "candidates.json"):
        p = os.path.join(DATA, fn)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        for sc in d.get("shichen", []):
            for key in ("poems", "candidates", "archived_imagery"):
                for e in sc.get(key, []):
                    if e.get("line"):
                        norms.add(norm_cjk(e["line"]))
    return norms


def get_t2s():
    """繁→简归一化函数(opencc t2s)。仅供**名录归一化**用,不转换语料。
    opencc 缺失时返回 None(调用方回退为不归一)。主编 2026-07-07 授权:
    作废的是「语料繁简转换」,名录(tang300 繁体)归一化另论,不违反该裁定。"""
    try:
        import opencc
        return opencc.OpenCC("t2s").convert
    except Exception as e:
        print("  [warn] opencc 不可用(%s),名录不归一,唐诗类 famous 退化为召回下限。" % e)
        return None


def load_anthologies(dirpath, t2s=None):
    """→ {famous_key: anthology_name}。key = 作者\\t题目 或 作者\\t#首句(均取汉字指纹)。
    《宋词三百首》本为简体;《唐诗三百首》为繁体,若传入 t2s 则**仅对该名录**做繁→简归一化
    后再建键(名录归一化,非语料转换)。t2s=None 时唐诗类仅题 / 作者恰同者命中(召回下限)。"""
    idx = {}
    for fn, name, normalize in (("tang300.json", "唐诗三百首", True),
                                ("song300.json", "宋词三百首", False)):
        path = os.path.join(dirpath, fn)
        if not os.path.exists(path):
            continue
        conv = t2s if (normalize and t2s) else (lambda x: x)
        for e in json.load(open(path, encoding="utf-8")):
            auth = norm_cjk(conv(e.get("author", "")))
            title = norm_cjk(conv(e.get("title") or e.get("rhythmic") or ""))
            paras = e.get("paragraphs") or []
            if auth and title:
                idx[auth + "\t" + title] = name
            if auth and paras:
                idx[auth + "\t#" + norm_cjk(conv(paras[0]))] = name
    return idx


# ───────────────────────── 文本工具(纯函数) ─────────────────────────
def norm_cjk(s):
    return "".join(CJK.findall(s or ""))


def clean_sentence(s):
    """句内半角标点→全角;去空白;去首尾切分符。"""
    s = (s or "").strip().strip("。！？!?；;，,、 ")
    for a, b in PUNCT_FULL.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def era_info(dynasty, fname):
    """(rank, bonus):rank 越小越古 / 越正典;优先看行内朝代字段,空则看文件名。"""
    t = (dynasty or "").strip() or (fname or "")
    if any(k in t for k in ("先秦", "诗经", "楚辞", "乐府", "汉")) or t == "秦":
        return (0, 3.0)
    if any(k in t for k in ("魏", "晋", "南北朝", "隋")):
        return (1, 3.0)
    if "唐" in t or "五代" in t:
        return (2, 3.0)
    if "宋" in t:
        return (3, 2.5)
    if any(k in t for k in ("金", "辽", "元")):
        return (4, 1.5)
    if "明" in t:
        return (5, 0.5)
    if "清" in t:
        return (6, 0.5)
    return (7, 0.0)


def shape_score(clauses):
    """句形分 + 标签。长句 / 碎片给负分(排除,连整联一起丢)。"""
    lens = [len(c) for c in clauses if c]
    if not lens:
        return (-100, "empty")
    mx = max(lens)
    n = len(lens)
    if mx > 12:
        return (-50, "long_clause")           # 超渲染硬约束(单句>16 数据错误)的危险区,整联丢
    if n == 1 and mx < 4:
        return (-30, "short_fragment")
    if n == 2 and lens[0] == lens[1] and lens[0] in (5, 7):
        return (3.0, "regular")               # 五 / 七言工对,最佳
    if n == 2 and lens[0] == lens[1] and lens[0] in (4, 6):
        return (2.0, "even")
    if n == 2 and all(3 <= x <= 9 for x in lens):
        return (1.5, "couplet")
    if n == 1 and 4 <= mx <= 9:
        return (1.0, "single")
    if all(3 <= x <= 11 for x in lens):
        return (0.8, "ok")
    return (0.3, "loose")


def word_quality(word, info):
    """词性分 + flags。单字 / 多义降权。"""
    flags = []
    if info["boundary"]:
        flags.append("boundary")
    if len(word) == 1:
        flags.append("single_char")
    if word in RISK_CONTEXT:
        flags.append("risky:" + word)
        q = 0.0 if word == "朝" else 0.8
    elif info["boundary"]:
        q = 1.5
    elif len(word) == 1:
        q = 1.0
    else:
        q = 2.0
    return q, flags


def literal_guess(word, sentence):
    """上下文反例初判:命中反例→suspect,否则 likely。仅提示,不裁决。"""
    for bad in RISK_CONTEXT.get(word, ()):
        if bad in sentence:
            return "suspect", "「%s」处于「%s」,疑非实指时刻" % (word, bad)
    if len(word) == 1 and word in RISK_CONTEXT:
        return "likely", "「%s」单字多义,请核是否实指时刻" % word
    return "likely", ""


def author_known(a):
    a = (a or "").strip()
    return bool(a) and a not in ("佚名", "无名氏", "失名", "无名", "未知")


def build_matcher(word_info):
    words = sorted(word_info.keys(), key=len, reverse=True)   # 最长匹配优先
    return re.compile("|".join(re.escape(w) for w in words))


def poem_famous(author, title, first_line, anthology_idx):
    """(bool, name):按 作者+题目 或 作者+#首句 命中名录。"""
    a = norm_cjk(author)
    if not a:
        return (False, "")
    for k in (a + "\t" + norm_cjk(title), a + "\t#" + norm_cjk(first_line)):
        if k in anthology_idx:
            return (True, anthology_idx[k])
    return (False, "")


# ───────────────────────── 抽取(纯函数,含自检) ─────────────────────────
def harvest_poem(title, content, author, dynasty, fname, word_info, matcher):
    """从一首诗的**正文**抽出所有命中时间词的句(联)。纯函数:无 I/O、无外部状态。
    返回 [hit,...];已按句形过滤(单句>12 字的整联、碎片直接不产出);未去重、未打分排序。
    题目不参与匹配(time_word 在题不在文者不算命中)。"""
    hits = []
    for raw_sent in SENT_SEP.split(content or ""):
        sent = clean_sentence(raw_sent)
        if len(sent) < 4:
            continue
        clauses = [c for c in CLAUSE_SEP.split(sent) if c]
        sscore, stag = shape_score(clauses)
        if sscore < 0:                    # 长句 / 碎片:整联丢弃
            continue
        for m in matcher.finditer(sent):
            word = m.group(0)
            info = word_info[word]
            lg, lg_reason = literal_guess(word, sent)
            hits.append({
                "line": sent,
                "time_word": word,
                "shichen": info["shichen"],
                "shape": stag,
                "shape_score": sscore,
                "boundary": info["boundary"],
                "auto_hint": lg,
                "auto_reason": lg_reason,
            })
    return hits


def run_selftest(word_info, matcher):
    """§2.2 硬要求:抽取 / 过滤纯函数 + 三样本精确期望。"""
    ok = True

    def check(name, cond, got=""):
        nonlocal ok
        print(("  [OK] " if cond else "  [NO] ") + name + ("" if cond else "  got=" + repr(got)))
        ok = ok and cond

    # 样本 A:长短句(词),正文含时间词「夜阑」→ 应抽出该联
    a = harvest_poem("十一月四日风雨大作", "夜阑卧听风吹雨，铁马冰河入梦来。",
                     "陆游", "宋", "宋_test.csv", word_info, matcher)
    check("A 词正文命中「夜阑」→ 1 联", len(a) == 1 and a[0]["time_word"] == "夜阑"
          and a[0]["line"] == "夜阑卧听风吹雨，铁马冰河入梦来" and a[0]["shichen"] == "hai", a)

    # 样本 B:时间词只在题目「日暮」,正文无 → 应无命中(不扫题目)
    b = harvest_poem("日暮", "空山不见人，但闻人语响。", "王维", "唐", "唐_test.csv", word_info, matcher)
    check("B 题含「日暮」正文无 → 0 命中", b == [], b)

    # 样本 C:单句 > 12 字含时间词「平明」→ 整联按句形丢弃
    c = harvest_poem("长句", "平明时节独行寻白羽终没在石棱之中", "卢纶", "唐", "唐_test.csv",
                     word_info, matcher)
    check("C 单句>12字含「平明」→ 整联丢弃 0 命中", c == [], c)

    print("自检(抽取纯函数):" + ("通过" if ok else "失败"))
    return ok


# ───────────────────────── 语料迭代 ─────────────────────────
def iter_rows(corpus_dir, only, limit):
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.csv")))
    if only:
        files = [p for p in files if any(k in os.path.basename(p) for k in only)]
    if not files:
        sys.exit("语料为空:%s 下无匹配 *.csv(--only=%s)。先跑 scripts/fetch_corpus.py。"
                 % (corpus_dir, only))
    for path in files:
        fname = os.path.basename(path)
        with open(path, encoding="utf-8", newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                if limit and i >= limit:
                    break
                yield fname, row


def source_hint(dynasty):
    d = dynasty or ""
    if "唐" in d:
        return "疑《全唐诗》,待核卷次"
    if "宋" in d:
        return "疑《全宋诗》/《全宋词》,待核"
    if any(k in d for k in ("先秦", "汉", "魏", "晋", "南北朝", "隋")):
        return "疑《先秦汉魏晋南北朝诗》/《乐府诗集》,待核"
    if "元" in d:
        return "疑《全元散曲》/《全元诗》,待核"
    if "明" in d or "清" in d:
        return "疑别集 / 断代总集,待核"
    return "待溯源"


# ───────────────────────── 主流程 ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(ROOT, "corpus", "werneror"))
    ap.add_argument("--anthology", default=os.path.join(ROOT, "corpus", "anthology"))
    ap.add_argument("--only", nargs="*", default=DEFAULT_ERAS, help="只扫文件名含这些子串的朝代")
    ap.add_argument("--per-shichen", type=int, default=20)
    ap.add_argument("--pool", type=int, default=800, help="每辰候选池上限")
    ap.add_argument("--out", default=os.path.join(DATA, "harvest", "batch-001.json"))
    ap.add_argument("--report", default=os.path.join(ROOT, "docs", "harvest-report.md"))
    ap.add_argument("--raw", default=os.path.join(DATA, "harvest.raw.jsonl"))
    ap.add_argument("--limit", type=int, default=0, help="每文件仅扫前 N 行(调试用,0=全扫)")
    ap.add_argument("--selftest", action="store_true", help="只跑纯函数自检后退出")
    args = ap.parse_args()

    word_info, shichen_meta = load_time_words()
    matcher = build_matcher(word_info)

    if args.selftest:
        sys.exit(0 if run_selftest(word_info, matcher) else 1)

    # 抽取自检先跑,不过不产出
    if not run_selftest(word_info, matcher):
        sys.exit("抽取自检未过,已中止。")

    existing = load_existing_norms()
    anthology_idx = load_anthologies(args.anthology, get_t2s())
    order = [sid for sid, _, _ in shichen_meta]

    seen = {sid: set() for sid in order}
    pool = {sid: [] for sid in order}          # heapq of (sortkey_tuple, tie, entry)
    n_match = {sid: 0 for sid in order}        # 命中总数(去重前,含被句形排除)
    n_distinct = {sid: 0 for sid in order}     # 去重后进 raw 的条目数
    n_famous = {sid: 0 for sid in order}
    word_hits = {}                             # (sid,word)→去重后条数,用于报告稀缺词
    dropped = {"in_library": 0, "dup": 0}
    scanned = 0
    tie = 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    rawf = open(args.raw, "w", encoding="utf-8")

    for fname, row in iter_rows(args.corpus, args.only, args.limit):
        scanned += 1
        content = row.get("内容") or ""
        if not content:
            continue
        author = (row.get("作者") or "").strip()
        dynasty = (row.get("朝代") or "").strip()
        title = (row.get("题目") or "").strip()
        erank, ebonus = era_info(dynasty, fname)
        aknown = author_known(author)
        tier = 1 if author in TIER1 else 2
        first_line = clean_sentence(SENT_SEP.split(content)[0])
        famous, anthology = poem_famous(author, title, first_line, anthology_idx)
        full_poem = clean_full(content)

        raw_hits = harvest_poem(title, content, author, dynasty, fname, word_info, matcher)
        for h in raw_hits:
            sid = h["shichen"]
            word = h["time_word"]
            n_match[sid] += 1
            key = norm_cjk(h["line"])
            if key in existing:
                dropped["in_library"] += 1
                continue
            if key in seen[sid]:
                dropped["dup"] += 1
                continue
            seen[sid].add(key)
            n_distinct[sid] += 1
            word_hits[(sid, word)] = word_hits.get((sid, word), 0) + 1
            if famous:
                n_famous[sid] += 1

            wq, wflags = word_quality(word, word_info[word])
            flags = list(wflags)
            if not aknown:
                flags.append("author_unknown")
            if h["auto_hint"] == "suspect":
                flags.append("literal_suspect")
            score = round(h["shape_score"] + ebonus + wq + (0.5 if aknown else 0.0), 3)
            # 排序键:famous > tier1 > tier2 > 综合分(降序)。heapq 取最大,故用可比元组。
            sortkey = (1 if famous else 0, 1 if tier == 1 else 0, score)

            entry = {
                "line": h["line"],
                "source": ("《%s》" % title) if title else "",
                "author": author or "佚名",
                "dynasty": dynasty or "",
                "time_word": word,
                "why": "",
                "confidence": "unverified",
                "source_note": "待溯源",            # 红线:Werneror 非出处
                "famous": famous,
                "anthology": anthology,
                "tier": tier,
                "semantic": {"verdict": None, "reason": "", "auto_hint": h["auto_hint"]},
                "full_poem": full_poem,
                "needs_review": True,
                "harvest": {
                    "matched_word": word,
                    "shape": h["shape"],
                    "score": score,
                    "flags": flags,
                    "auto_hint": h["auto_hint"],
                    "auto_reason": h["auto_reason"],
                    "boundary": h["boundary"],
                    "corpus_ref": {"tool": "Werneror/Poetry", "file": fname, "note": "检索工具,非出处"},
                    "source_hint": source_hint(dynasty),
                },
            }
            rawf.write(json.dumps({"shichen": sid, "sortkey": sortkey, **entry}, ensure_ascii=False) + "\n")
            tie += 1
            heapq.heappush(pool[sid], (sortkey, tie, entry))
            if len(pool[sid]) > args.pool:
                heapq.heappop(pool[sid])

    rawf.close()

    # 组装 batch:每辰取头部 per-shichen 条
    out_shichen, total_head = [], 0
    per = {}
    for sid, name, alias in shichen_meta:
        ranked = heapq.nlargest(args.per_shichen, pool[sid], key=lambda t: (t[0], -t[1]))
        cands = [e for _, _, e in ranked]
        total_head += len(cands)
        head_famous = sum(1 for e in cands if e["famous"])
        per[sid] = {"name": name, "alias": alias, "hits": n_match[sid],
                    "distinct": n_distinct[sid], "head": len(cands),
                    "famous": head_famous, "famous_distinct": n_famous[sid]}
        out_shichen.append({"id": sid, "name": name, "alias": alias, "candidates": cands})

    out = {
        "meta": {
            "type": "harvest",
            "batch": "001",
            "generated_by": "scripts/harvest_time_words.py",
            "corpus": "Werneror/Poetry(检索工具,非出处;晋升前须逐句对通行本核字)",
            "eras": args.only,
            "gate": "闸门后待审批次。严禁直接并入 poems.json / candidates.json;须由主编逐句对通行本 / "
                    "权威选本核字、补真实 source_note(如《全唐诗》卷次)后,再手动晋升。",
            "source_note_policy": "harvested 一律「待溯源」;harvest.source_hint 仅为便于查证的非权威线索。",
            "ranking": "famous(唐诗/宋词三百首) > tier1(一线名家) > tier2 > 句形/时代/词性综合分。",
            "quota": "每时辰头部前 %d 条,总量上限 240,宁缺毋滥。" % args.per_shichen,
            "raw": "全量去重命中见 data/harvest.raw.jsonl(gitignore);稀缺时辰可回 raw 续淘。",
            "semantic": "batch[].semantic.verdict 由逐条人工标注:实指时刻 keep / 虚指人名地名 drop + 理由;"
                        "auto_hint 仅参考。只注不裁,主编终裁。",
            "counts": {"scanned_poems": scanned, "head_total": total_head,
                       "per_shichen": per, "dropped": dropped},
        },
        "shichen": out_shichen,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    write_report(args.report, shichen_meta, per, word_info, word_hits, out_shichen,
                 scanned, total_head, dropped, anthology_idx, args.only)

    # ── 产出后自检:三条硬不变量 ──
    bad = 0
    for sc in out_shichen:
        legal = {w for w, i in word_info.items() if i["shichen"] == sc["id"]}
        for e in sc["candidates"]:
            if e["time_word"] not in e["line"]:
                print("!! time_word 非 line 子串:", e["line"]); bad += 1
            if e["time_word"] not in legal:
                print("!! time_word 不属该时辰词表:", e["line"]); bad += 1
            if norm_cjk(e["line"]) in existing:
                print("!! 与既有曲库重复:", e["line"]); bad += 1

    print("扫描 %d 首;命中(去重后)%d 条;头部 %d 条 → %s"
          % (scanned, sum(n_distinct.values()), total_head, args.out))
    for sid, name, _ in shichen_meta:
        c = per[sid]
        print("  %-4s %s hits=%-7d distinct=%-6d head=%-3d famous=%d"
              % (sid, name, c["hits"], c["distinct"], c["head"], c["famous"]))
    print("丢弃:", dropped, " 名录条目:", len(anthology_idx))
    print("自检:", "通过(3 条硬不变量)" if bad == 0 else ("发现 %d 处违规" % bad))
    sys.exit(1 if bad else 0)


def clean_full(content):
    """整诗简体全文,半角标点归全角,压到单行(供主编核字对照)。"""
    s = re.sub(r"\s+", "", content or "")
    for a, b in PUNCT_FULL.items():
        s = s.replace(a, b)
    return s[:400]


def write_report(path, shichen_meta, per, word_info, word_hits, out_shichen,
                 scanned, total_head, dropped, anthology_idx, eras):
    L = []
    L.append("# 曲库采收报告 · batch-001\n")
    L.append("> 语料:Werneror/Poetry(检索工具,非出处)。朝代范围:%s。" % "、".join(eras))
    L.append("> 扫描 %d 首,去重后命中 %d 条,头部入批 %d 条(每辰≤20,总≤240)。" %
             (scanned, sum(v["distinct"] for v in per.values()), total_head))
    L.append("> 丢弃:与既有曲库重复 %d、跨批去重 %d。名录条目 %d。\n" %
             (dropped["in_library"], dropped["dup"], len(anthology_idx)))
    L.append("**闸门**:本批一律 `source_note=待溯源`;晋升前主编须逐句对通行本 / 权威选本核字。\n")

    # 各时辰命中量
    L.append("## 各时辰命中量\n")
    L.append("| 时辰 | 别名 | 命中(去重前) | 去重后 | 入批头部 | famous |")
    L.append("|---|---|---:|---:|---:|---:|")
    for sid, name, alias in shichen_meta:
        c = per[sid]
        L.append("| %s | %s | %d | %d | %d | %d |" %
                 (name, alias, c["hits"], c["distinct"], c["head"], c["famous"]))

    # 供给稀缺的时辰
    scarce = sorted(shichen_meta, key=lambda m: per[m[0]]["distinct"])[:4]
    L.append("\n## 供给稀缺的时辰(去重后命中最少)\n")
    for sid, name, alias in scarce:
        L.append("- **%s(%s)**:去重后仅 %d 条。" % (name, alias, per[sid]["distinct"]))

    # 各时辰内稀缺的词(该时辰词表里命中为 0 或个位数的词)
    L.append("\n## 稀缺词(各时辰词表内命中偏少 / 为 0 的词)\n")
    for sid, name, alias in shichen_meta:
        words = [w for w, i in word_info.items() if i["shichen"] == sid]
        rows = sorted(((word_hits.get((sid, w), 0), w) for w in words))
        zero = [w for c, w in rows if c == 0]
        low = ["%s(%d)" % (w, c) for c, w in rows if 0 < c <= 3]
        seg = []
        if zero:
            seg.append("0 命中:" + "、".join(zero))
        if low:
            seg.append("≤3:" + "、".join(low))
        if seg:
            L.append("- %s:%s" % (name, ";".join(seg)))

    # famous 命中率
    fam = sum(v["famous"] for v in per.values())
    L.append("\n## famous 命中率\n")
    L.append("- 头部入批共 %d 条,其中 famous(命中《唐诗三百首》/《宋词三百首》名录)%d 条,占 %.1f%%。" %
             (total_head, fam, 100.0 * fam / total_head if total_head else 0.0))
    L.append("- 说明:《唐诗三百首》原文繁体,已按主编 2026-07-07 授权对**名录**做繁→简归一化(opencc t2s,"
             "仅名录、不转语料)后与简体语料精确匹配;《宋词三百首》本简体,按「作者+首句」命中。opencc 缺失时回退为召回下限。")
    L.append("- tier(一线名家表,作者名简体匹配,稳定)已作主排序,不受繁简影响。")

    # 误命中抽样:auto_hint=suspect 的头部条目
    L.append("\n## 误命中抽样(auto_hint=suspect,疑非实指时刻,待人工核)\n")
    n = 0
    for sc in out_shichen:
        for e in sc["candidates"]:
            if e["semantic"]["auto_hint"] == "suspect" and n < 15:
                L.append("- 〔%s〕「%s」— %s(%s《%s》)" %
                         (sc["name"], e["time_word"], e["line"],
                          e["author"], e["source"].strip("《》")))
                n += 1
    if n == 0:
        L.append("- (头部无 suspect 命中。)")

    L.append("\n## 曲库单一能被数据解决到什么程度\n")
    L.append("- 直书时间词的名句,常见时辰(卯 / 辰 / 戌 / 子 / 酉)供给充足,数据检索即可批量供给;")
    L.append("- 冷僻时辰(巳 / 申 / 亥 / 未)与冷僻词(见上「稀缺词」)供给单薄,难靠检索补齐,")
    L.append("  须人工从别集 / 类书按意象反查,或放宽体裁 —— 这部分是数据解决不了、要人来补的。")
    L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
