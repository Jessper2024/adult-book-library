#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分卷规划器（只算不建）：按「分组 → 年份 → 卷」算出该出哪些书。

规则（2026-09-16 陈少定）：
  - 分卷上限 50 部；分组（单人/双人/多人/无码）→ 年份 → 卷（第N卷）→ 月 → 编号
  - 卷的边界按月份范围切（从 1 月起按月累加，接近但不超 50 切一刀），月份连续、落在整月
  - 某年 ≤50 部直接出 {年}年版；超了才切卷
  - 书名带月份范围：{演员}{分组}作品集{年}年第一卷（1月-6月）
  - 书内 h1 = 月份（正序）

用法:
    python3 plan_volumes.py --dir "~/Life/成人图书创建/北原夏美/xhtml 文稿" --actor 北原夏美
    python3 plan_volumes.py --dir ... --actor 北原夏美 --emit-cmds   # 顺便打印生成命令
"""
import argparse
import collections
import os
import re

LIMIT = 50
NAME_RE = re.compile(r"^(无码_)?(单人|双人|多人)_(\d{4})年(\d{1,2})月")


def scan(src_dir):
    """返回 {(分组, 年): {月: 部数}}，分组含 无码_单人 这种合成键"""
    stat = collections.defaultdict(lambda: collections.Counter())
    unknown = collections.Counter()
    for name in os.listdir(src_dir):
        m = NAME_RE.match(name)
        if not m:
            if "_0000-00-00_" in name:          # 源站没标发行日期的，单独归一本
                unknown["日期未标注"] += 1
            else:
                unknown["(文件名不合规则)"] += 1
            continue
        tag, grp, year, mon = m.group(1) or "", m.group(2), int(m.group(3)), int(m.group(4))
        # 无码组内部扁平，不再拆单人/多人（沿用 epub 里的无码规则）
        cat = "无码" if tag else grp
        if year == 0:                       # 0000年0月0日 这类无效日期
            unknown[cat] += 1
            continue
        stat[(cat, year)][mon] += 1
    return stat, unknown


_CN = "零一二三四五六七八九"


def cn_num(n):
    """1 → 一，11 → 十一，25 → 二十五（卷号用中文数字）"""
    if n < 10:
        return _CN[n]
    if n < 20:
        return "十" + (_CN[n - 10] if n > 10 else "")
    if n < 100:
        return _CN[n // 10] + "十" + (_CN[n % 10] if n % 10 else "")
    return str(n)


def split_volumes(months, limit=LIMIT):
    """months: [(月, 部数)] 升序。贪心切卷，每卷 ≤ limit 且月份连续。
    返回 [(起始月, 结束月, 部数, 是否需要再拆)]"""
    vols, cur, cur_n = [], [], 0
    for mon, cnt in months:
        if cnt > limit:                     # 单月就超，先单独成一卷并标记
            if cur:
                vols.append((cur[0], cur[-1], cur_n, False))
                cur, cur_n = [], 0
            vols.append((mon, mon, cnt, True))
            continue
        if cur and cur_n + cnt > limit:
            vols.append((cur[0], cur[-1], cur_n, False))
            cur, cur_n = [], 0
        cur.append(mon)
        cur_n += cnt
    if cur:
        vols.append((cur[0], cur[-1], cur_n, False))
    return vols


def plan(src_dir, actor, limit=LIMIT):
    stat, unknown = scan(src_dir)
    books = []

    # 整组总数 ≤ 上限的（如双人、无码、小演员的单人），直接出组级一本，不按年份切
    cats = {}
    for (cat, year) in stat:
        cats.setdefault(cat, 0)
        cats[cat] += sum(stat[(cat, year)].values())
    for cat in sorted(cats):
        if cats[cat] <= limit and cats[cat] > 0:
            books.append({
                "title": f"{actor}{cat}作品集", "cat": cat, "year": None,
                "n": cats[cat], "lo": None, "hi": None, "filter": cat,
                "range": None, "split": False,
            })

    for (cat, year) in sorted(stat, key=lambda k: (k[0], k[1])):
        if cats[cat] <= limit:              # 已出组级一本，不再按年份切
            continue
        months = sorted(stat[(cat, year)].items())
        total = sum(c for _, c in months)
        # 双人/无码部数少时保持组级一本（沿用现做法）
        if total <= limit:
            books.append({
                "title": f"{actor}{cat}作品集{year}年版", "cat": cat, "year": year,
                "n": total, "lo": None, "hi": None, "filter": f"{cat}_{year}年",
                "range": None, "split": False,
            })
            continue
        for i, (lo, hi, n, need_split) in enumerate(split_volumes(months, limit), 1):
            span = f"{lo}月" if lo == hi else f"{lo}月-{hi}月"
            tail = "⚠单月超限需再拆" if need_split else ""
            books.append({
                "title": f"{actor}{cat}作品集{year}年第{cn_num(i)}卷（{span}）{tail}",
                "cat": cat, "year": year, "n": n, "lo": lo, "hi": hi,
                "filter": f"{cat}_{year}年", "range": f"{lo}-{hi}",
                "split": need_split,
            })
    # 源站没标发行日期的（0000-00-00）单独出一本，保证分卷覆盖全部作品
    if unknown.get("日期未标注"):
        books.append({
            "title": f"{actor}日期未标注作品集", "cat": "日期未标注", "year": None,
            "n": unknown["日期未标注"], "lo": None, "hi": None,
            "filter": "*_0000-00-00*", "range": None, "split": False,
        })
    return books, unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="xhtml 文稿目录")
    ap.add_argument("--actor", required=True, help="演员名（用于拼书名）")
    ap.add_argument("--limit", type=int, default=LIMIT)
    ap.add_argument("--emit-cmds", action="store_true", help="打印对应的生成命令")
    args = ap.parse_args()

    src = os.path.expanduser(args.dir)
    books, unknown = plan(src, args.actor, args.limit)
    print(f"=== {args.actor} 分卷规划（上限 {args.limit} 部/本）===")
    print(f"{'书名':44} {'部数':>5}  命令参数")
    for b in books:
        cmd = f'--filter "{b["filter"]}"' + (f' --month-range "{b["range"]}"' if b["range"] else "")
        flag = "  ⚠ 单月超 50，需要 -1/-2 再拆" if b["split"] else ""
        print(f'{b["title"]:44} {b["n"]:>5}  {cmd}{flag}')
    print("-" * 78)
    print(f"合计 {len(books)} 本，{sum(b['n'] for b in books)} 部")
    rest = {k: v for k, v in unknown.items() if k != "日期未标注"}
    if rest:
        print("未纳入（需单独处理）:", rest)

    if args.emit_cmds:
        print("\n--- 生成命令 ---")
        for b in books:
            mr = f' --month-range "{b["range"]}"' if b["range"] else ""
            print(f'$PY sigil_epub_build.py --dir "{src}" --out "$OUT" '
                  f'--title "{b["title"]}" --filter "{b["filter"]}"{mr} '
                  f'--group-by month --cover "$COVER" --no-open')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
