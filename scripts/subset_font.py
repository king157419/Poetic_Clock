#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诗意时钟 · 字体子集化
======================

用 fonttools 对「霞鹜文楷(LXGW WenKai)」按 data/poems.json 中实际出现的字符
加上界面文字做子集化,输出自托管 woff2(目标 < 300KB)。

为什么要子集化:
    完整的 LXGW WenKai 覆盖数万汉字,约 20MB+;而本时钟只用到几百个字。
    子集后体积骤降到一两百 KB,断网也能秒开,且完全自托管(不碰 Google Fonts,
    大陆可用)。

用法:
    1) 准备好源字体(任选其一):
         a. 手动下载 LXGWWenKai-Regular.ttf 放到 fonts/ 下;或
         b. 运行时加 --download,脚本自动从 GitHub Release 拉取到 fonts/。
    2) 安装依赖:  pip install fonttools brotli
    3) 生成子集:  python scripts/subset_font.py            # 源字体在 fonts/ 下
       或        python scripts/subset_font.py --download  # 顺便自动下载源字体

产物: fonts/LXGWWenKai-subset.woff2

字符集 = data/poems.json 中所有字符 ∪ 界面文字 ∪ ASCII ∪ 常用标点。
以后主人替换或新增诗句后,重跑本脚本即可让新字进入子集(见 README「加一句诗」)。
"""

import argparse
import json
import os
import sys
import urllib.request

# Windows 控制台默认可能是 GBK/cp1252,直接 print 中文会崩;统一按 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ---- 路径 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
POEMS = os.path.join(ROOT, "data", "poems.json")
FONTS_DIR = os.path.join(ROOT, "fonts")
DEFAULT_SRC = os.path.join(FONTS_DIR, "LXGWWenKai-Regular.ttf")
DEFAULT_OUT = os.path.join(FONTS_DIR, "LXGWWenKai-subset.woff2")

# 与源字体同版本;如需更新版本,改这里即可。
FONT_VERSION = "v1.522"
FONT_URL = (
    "https://github.com/lxgw/LxgwWenKai/releases/download/"
    f"{FONT_VERSION}/LXGWWenKai-Regular.ttf"
)

# 界面上会出现、但不在 poems.json 里的文字(角标、提示、错误信息、印章等)。
UI_TEXT = (
    "预览"                       # 预览角标
    "诗集未能载入请用本地静态服务器打开见误"  # 数据加载失败时的兜底文案
    "其他时辰"                    # 提示语「← → 预览其他时辰」
    "子丑寅卯辰巳午未申酉戌亥"       # 印章单字(十二时辰名首字,已在 names 中,冗余保险)
)

# 常用标点与符号(渲染中可能出现:间隔号、全角空格、箭头、书名号、括号、冒号等)。
PUNCT = "·　：、，。！？；—…（）〔〕【】《》〈〉「」『』‘’“”←→〇"

# 基本 ASCII(数字、字母、括号——错误文案里含 “README” 等)。
ASCII = "".join(chr(c) for c in range(0x20, 0x7F))


def collect_chars_from_json(path):
    """递归收集 poems.json 中所有字符串里出现过的字符。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chars = set()

    def walk(node):
        if isinstance(node, str):
            chars.update(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return chars


def build_charset():
    chars = collect_chars_from_json(POEMS)
    chars.update(UI_TEXT)
    chars.update(PUNCT)
    chars.update(ASCII)
    # 去掉控制字符与换行,保留可见字符
    chars = {c for c in chars if c.isprintable() and not c.isspace() or c in ("　",)}
    return chars


def maybe_download(src_path, do_download):
    if os.path.exists(src_path):
        return src_path
    if not do_download:
        sys.exit(
            "找不到源字体:%s\n"
            "请手动下载后放到 fonts/,或加 --download 让脚本自动拉取。\n"
            "下载地址:%s" % (src_path, FONT_URL)
        )
    os.makedirs(os.path.dirname(src_path), exist_ok=True)
    print("正在下载源字体(约 25MB)…\n  %s" % FONT_URL)
    urllib.request.urlretrieve(FONT_URL, src_path)
    print("已保存到 %s" % src_path)
    return src_path


def main():
    ap = argparse.ArgumentParser(description="LXGW WenKai 子集化 for 诗意时钟")
    ap.add_argument("--font", default=DEFAULT_SRC, help="源字体路径(默认 fonts/LXGWWenKai-Regular.ttf)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 woff2 路径")
    ap.add_argument("--download", action="store_true", help="源字体缺失时自动从 GitHub 下载")
    args = ap.parse_args()

    # fonttools 依赖延迟到此处再导入,便于在缺依赖时给出友好提示。
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        sys.exit("缺少依赖,请先运行:pip install fonttools brotli")

    src = maybe_download(args.font, args.download)

    charset = build_charset()
    text = "".join(sorted(charset))
    print("子集字符数:%d" % len(charset))

    options = subset.Options()
    options.flavor = "woff2"          # 直接输出 woff2(需 brotli)
    options.desubroutinize = True
    options.layout_features = ["*"]   # 保留必要的排版特性
    options.name_IDs = ["*"]
    options.recalc_bounds = True
    options.drop_tables = []          # 交由 fonttools 默认精简

    font = subset.load_font(src, options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    subset.save_font(font, args.out, options)
    font.close()

    size = os.path.getsize(args.out)
    kb = size / 1024.0
    print("已输出:%s" % args.out)
    print("体积:%.1f KB  (%d 字节)" % (kb, size))
    if size >= 300 * 1024:
        print("⚠️  超过 300KB 目标,请检查字符集是否过大。")
        sys.exit(2)
    print("✓ 小于 300KB 目标。")


if __name__ == "__main__":
    main()
