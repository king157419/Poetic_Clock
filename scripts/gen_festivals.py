#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 节令表生成
=====================

生成 data/festivals.json:2026–2035 年各农历节日的**公历**日期表,供节令彩蛋
(selectPoem 的节日层)查表使用。

铁律:农历→公历日期**只许来自库计算,严禁手写、严禁凭记忆**。本脚本用
`lunardate` 计算,并内置锚点断言:2026 春节必须等于 2026-02-17,不等即报错退出。

用法:
    pip install lunardate
    python scripts/gen_festivals.py

产物:data/festivals.json,结构 { "meta": {...}, "dates": { "YYYY-MM-DD": ["节日名"] } }。
重新生成(如扩展年份):改下方 START/END 后重跑本脚本即可。
"""

import sys
import os
import json
import datetime

# Windows 控制台默认可能是 GBK/cp1252,直接 print 中文会崩;统一 UTF-8 输出。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    from lunardate import LunarDate
except ImportError:
    sys.exit("缺少依赖,请先运行:pip install lunardate")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "festivals.json")
START, END = 2026, 2035

# 农历(月, 日) → 节日名。除夕单独处理(正月初一前一天)。
LUNAR = [
    (1, 1, "春节"),
    (1, 15, "元宵"),
    (5, 5, "端午"),
    (7, 7, "七夕"),
    (8, 15, "中秋"),
    (9, 9, "重阳"),
]


def solar(lunar_year, month, day):
    """农历 → 公历 date(库计算)。兼容新旧 API。"""
    ld = LunarDate(lunar_year, month, day)
    fn = getattr(ld, "to_solar_date", None) or getattr(ld, "toSolarDate")
    return fn()


def main():
    # ── 锚点断言:2026 春节必须等于 2026-02-17 ──
    anchor = solar(2026, 1, 1)
    if anchor != datetime.date(2026, 2, 17):
        sys.exit("锚点校验失败:2026 春节应为 2026-02-17,库算得 %s —— 请勿使用本次结果。" % anchor)
    print("锚点通过:2026 春节 = %s" % anchor)

    table = {}

    def add(dt, name):
        if dt is None or not (START <= dt.year <= END):
            return
        key = dt.isoformat()
        table.setdefault(key, [])
        if name not in table[key]:
            table[key].append(name)

    # 跨足够的农历年,确保落在 [START, END] 公历区间内的节日都被覆盖(含跨年的除夕)。
    for ly in range(START - 1, END + 2):
        for (m, d, name) in LUNAR:
            try:
                add(solar(ly, m, d), name)
            except Exception:
                pass
        # 除夕 = 该农历年正月初一的前一天
        try:
            add(solar(ly, 1, 1) - datetime.timedelta(days=1), "除夕")
        except Exception:
            pass

    out = {
        "meta": {
            "generated_by": "scripts/gen_festivals.py (lunardate)",
            "range": "%d-%d" % (START, END),
            "anchor": "2026 春节 = 2026-02-17",
            "note": "农历→公历由库计算,请勿手改;重新生成见 README「节令表」。"
        },
        "dates": {k: table[k] for k in sorted(table)}
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("已写入 %s(%d 个节日日期,%d–%d)" % (OUT, len(table), START, END))


if __name__ == "__main__":
    main()
