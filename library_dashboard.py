#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成人图书创建 · 数据看板

扫 ~/Life/成人图书创建/ 下每个演员目录，汇总：
  CSV 数据源条数 / 已抓 xhtml 数 / epub 本数与部数 / 体积 / 封面 / 分组与年份分布

产出自包含 HTML：~/Life/成人图书创建/_数据看板.html

用法:
    python3 library_dashboard.py
    python3 library_dashboard.py --root "~/Life/成人图书创建" --out "…/_数据看板.html"
"""
import argparse
import collections
import csv
import datetime as dt
import glob
import html
import os
import re
import zipfile

CAT_ORDER = ["单人", "双人", "多人", "无码", "日期未标注"]
NAME_RE = re.compile(r"^(无码_)?(单人|双人|多人)_(\d{4})年")


def human(n):
    """字节 → 人类可读"""
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def read_csv_rows(path):
    try:
        return list(csv.DictReader(open(path, encoding="utf-8-sig")))
    except Exception:
        return []


def scan_actor(actor_dir, actor):
    d = {"name": actor, "path": actor_dir}

    # ---- CSV 数据源 ----
    csvs = sorted(glob.glob(os.path.join(actor_dir, "*.csv")))
    main = os.path.join(actor_dir, f"{actor}作品集.csv")
    rows = read_csv_rows(main) if os.path.exists(main) else []
    d["csv_files"] = [(os.path.basename(c), len(read_csv_rows(c))) for c in csvs]
    d["csv_total"] = len(rows)
    # 演员列分布（单人 = 演员本人）
    cnt = collections.Counter()
    for r in rows:
        a = (r.get("演員") or "").strip()
        cnt["单人" if a == actor else ("多人" if a == "多人" else a or "?")] += 1
    d["csv_actor_split"] = cnt

    # ---- xhtml 文稿 ----
    xdir = os.path.join(actor_dir, "xhtml 文稿")
    names = [f for f in os.listdir(xdir)] if os.path.isdir(xdir) else []
    names = [f for f in names if f.endswith((".xhtml", ".html"))]
    d["xhtml"] = len(names)
    groups, years = collections.Counter(), collections.Counter()
    for n in names:
        m = NAME_RE.match(n)
        if not m:
            if "_0000-00-00_" in n:
                groups["日期未标注"] += 1
            else:
                groups["?"] += 1
            continue
        g = "无码" if m.group(1) else m.group(2)
        groups[g] += 1
        y = m.group(3)
        years["日期未标注" if y == "0000" else y] += 1
    d["groups"] = groups
    d["years"] = years

    # ---- epub ----
    books = []
    for ep in sorted(glob.glob(os.path.join(actor_dir, "*.epub"))):
        b = {"file": os.path.basename(ep), "size": os.path.getsize(ep)}
        try:
            z = zipfile.ZipFile(ep)
            nav = z.read("OEBPS/nav.xhtml").decode("utf-8", "replace")
            top = len(re.findall(r"<li><a[^>]*>[^<]*</a><ol>", nav))
            b["groups"] = top or nav.count("<li>")
            b["works"] = nav.count("<li>") - b["groups"]
            opf = z.read("OEBPS/content.opf").decode("utf-8", "replace")
            m = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf)
            s = re.search(r'property="file-as">([^<]*)<', opf)
            b["author"] = m.group(1) if m else "—"
            b["sort"] = s.group(1) if s else "—"
            b["cover"] = any(x.startswith("OEBPS/Images/cover.") for x in z.namelist())
            h1 = re.findall(r"<h1[^>]*>([^<]+)</h1>", nav)
            b["h1"] = h1[:1]
        except Exception as e:
            b.update({"groups": 0, "works": 0, "author": "—", "sort": "—",
                      "cover": False, "h1": []})
        books.append(b)
    d["books"] = books
    d["epub_size"] = sum(b["size"] for b in books)
    d["cover_file"] = next((os.path.basename(c) for c in
                            glob.glob(os.path.join(actor_dir, "封面.*")) +
                            glob.glob(os.path.join(actor_dir, "cover.*"))), None)
    return d


# 日志文件名 → 演员（进程已死时靠它认人）
LOG_ACTOR = {"julia": "京香Julia", "kinoshita": "木下凛凛子",
             "natsumi": "北原夏美", "maki": "北条麻妃",
             "hjmf": "北条麻妃", "nakamori": "中森玲子"}


def scan_tasks():
    """扫 /tmp 下的抓取日志，配上 pgrep 判断进程是否还活着。
    返回 [(任务信息)]：进度 / 完成·跳过·失败 / 速率·ETA / 状态"""
    import subprocess
    try:
        ps = subprocess.run(["pgrep", "-fl", "javbus_to_sigil"],
                            capture_output=True, text=True, timeout=15).stdout
    except Exception:
        ps = ""
    running = {}
    for line in ps.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)", line)
        if not m:
            continue
        pid, cmd = m.group(1), m.group(2)
        lg = re.search(r">\s*(/\S+\.log)", cmd)
        od = re.search(r'--out\s+"([^"]+)"', cmd) or re.search(r"--out\s+(\S+)", cmd)
        # 只有 shell wrapper 那行带 "> /tmp/xxx.log"；同一日志多行时保留信息最全的
        if lg and lg.group(1) not in running:
            running[lg.group(1)] = {
                "pid": pid,
                "dir": os.path.basename(os.path.dirname(od.group(1))) if od else "?",
            }

    tasks = []
    cands = sorted(set(glob.glob("/tmp/*_run*.log") + glob.glob("/tmp/hjmf_run.log")))
    for log in cands:
        try:
            txt = open(log, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        nums = re.findall(r"\[(\d+)/(\d+)\]", txt)
        if not nums:
            continue
        cur, total = int(nums[-1][0]), int(nums[-1][1])
        st = os.stat(log)
        now = dt.datetime.now().timestamp()
        alive = log in running
        age = now - st.st_mtime
        # macOS 的 st_ctime 不是创建时间，用 st_birthtime
        born = getattr(st, "st_birthtime", st.st_ctime)
        rate = cur / max(1, (st.st_mtime - born) / 60) if cur else 0
        eta = (total - cur) / rate if rate > 0 and cur < total else 0
        stem = os.path.basename(log)[:-4]
        guess = next((v for k, v in LOG_ACTOR.items() if k in stem), "(未知)")
        tasks.append({
            "log": os.path.basename(log),
            "actor": running.get(log, {}).get("dir") or guess,
            "cur": cur, "total": total,
            "done": txt.count("完成"), "skip": txt.count("已存在，跳过"),
            "fail": len(re.findall(r"失败", txt)),
            "alive": alive, "age": age, "rate": rate, "eta": eta,
            "pid": running.get(log, {}).get("pid"),
        })
    tasks.sort(key=lambda t: (not t["alive"], t["log"]))
    return tasks


def bar(pct, color="#7F77DD"):
    w = max(0, min(100, pct))
    return (f'<div class="bar"><div class="fill" style="width:{w:.1f}%;'
            f'background:{color}"></div></div>')


def build_html(all_data, out_path):
    total_csv = sum(d["csv_total"] for d in all_data)
    total_xhtml = sum(d["xhtml"] for d in all_data)
    total_books = sum(len(d["books"]) for d in all_data)
    total_size = sum(d["epub_size"] for d in all_data)
    total_works = sum(b["works"] for d in all_data for b in d["books"]
                      if b["file"] == f"{d['name']}作品集.epub")

    P = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>成人图书创建 · 数据看板</title><style>',
         'body{font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:28px;'
         'background:#F7F6F3;color:#2C2C2A;line-height:1.6}',
         'h1{font-size:22px;font-weight:500;margin:0 0 4px}',
         '.sub{color:#5F5E5A;font-size:13px;margin-bottom:22px}',
         '.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));'
         'gap:12px;margin-bottom:26px}',
         '.card{background:#fff;border:1px solid #E5E3DC;border-radius:12px;padding:14px 16px}',
         '.card .n{font-size:26px;font-weight:500;line-height:1.2}',
         '.card .l{font-size:12px;color:#5F5E5A;margin-top:2px}',
         '.actor{background:#fff;border:1px solid #E5E3DC;border-radius:14px;'
         'padding:18px 20px;margin-bottom:18px}',
         '.actor h2{font-size:17px;font-weight:500;margin:0 0 2px}',
         '.meta{font-size:12px;color:#5F5E5A;margin-bottom:12px}',
         '.bar{height:7px;background:#EFEDE6;border-radius:4px;overflow:hidden;margin:6px 0 10px}',
         '.fill{height:100%;border-radius:4px}',
         'table{width:100%;border-collapse:collapse;font-size:13px}',
         'th{text-align:left;font-weight:500;color:#5F5E5A;font-size:12px;'
         'padding:6px 8px;border-bottom:1px solid #E5E3DC}',
         'td{padding:6px 8px;border-bottom:1px solid #F0EEE8}',
         'tr:last-child td{border-bottom:none}',
         '.num{text-align:right;font-variant-numeric:tabular-nums}',
         '.tag{display:inline-block;background:#F1EFE8;border-radius:6px;'
         'padding:1px 7px;margin:0 4px 4px 0;font-size:12px;color:#444441}',
         '.ok{color:#0F6E56}.no{color:#A32D2D}',
         'details{margin-top:10px}summary{cursor:pointer;font-size:13px;color:#5F5E5A}',
         'details table{margin-top:8px}',
         '.foot{color:#888780;font-size:12px;margin-top:24px;text-align:center}',
         '</style></head><body>']

    P.append(f'<h1>成人图书创建 · 数据看板</h1>')
    P.append(f'<div class="sub">生成于 {dt.datetime.now():%Y-%m-%d %H:%M} · '
             f'数据源 <code>~/Life/成人图书创建/</code> · 重新统计：运行 '
             f'<code>library_dashboard.py</code></div>')

    # ---- 后台任务监控 ----
    tasks = scan_tasks()
    if tasks:
        P.append('<div class="actor" style="border-color:#CECBF6">')
        P.append('<h2>后台任务监控</h2>')
        P.append('<div class="meta">扫描 <code>/tmp/*_run*.log</code> + '
                 '<code>pgrep</code> 判定存活</div>')
        def rows(ts):
            out = []
            for t in ts:
                pct = t["cur"] / t["total"] * 100 if t["total"] else 0
                if t["alive"]:
                    state = ('<span class="ok">● 运行中</span>' if t["age"] < 180
                             else '<span class="no">● 疑似卡住</span>')
                else:
                    state = ('<span class="ok">✓ 完成</span>' if t["cur"] >= t["total"]
                             else '<span class="no">■ 已停止</span>')
                eta = f'{t["eta"]:.0f} 分' if t["eta"] else "—"
                rate = f'{t["rate"]:.1f}/分' if t["rate"] else "—"
                pid = f' · PID {t["pid"]}' if t.get("pid") else ""
                out.append(
                    f'<tr><td>{html.escape(t["actor"])}'
                    f'<div class="meta">{html.escape(t["log"])}{pid}</div></td>'
                    f'<td style="min-width:150px">{bar(pct)}'
                    f'<div class="meta">{t["cur"]}/{t["total"]}（{pct:.0f}%）</div></td>'
                    f'<td class="num">{t["done"]}</td><td class="num">{t["skip"]}</td>'
                    f'<td class="num">{t["fail"]}</td><td class="num">{rate}</td>'
                    f'<td class="num">{eta}</td><td>{state}</td></tr>')
            return "".join(out)

        head = ('<table><tr><th>任务</th><th>进度</th><th class="num">完成</th>'
                '<th class="num">跳过</th><th class="num">失败</th>'
                '<th class="num">速率</th><th class="num">预计还需</th>'
                '<th>状态</th></tr>')
        active = [t for t in tasks if t["alive"] or t["cur"] < t["total"]]
        finished = [t for t in tasks if not t["alive"] and t["cur"] >= t["total"]]
        P.append(head + rows(active) + '</table>')
        if finished:
            P.append(f'<details><summary>已完成任务（{len(finished)} 个）</summary>'
                     + head + rows(finished) + '</table></details>')
        P.append('</div>')
    P.append('<div class="cards">')
    for n, l in [(len(all_data), "演员"), (total_csv, "CSV 作品总数"),
                 (total_xhtml, "已生成 xhtml"), (total_books, "epub 本数"),
                 (human(total_size) if total_size else "0", "epub 总体积")]:
        P.append(f'<div class="card"><div class="n">{n}</div><div class="l">{l}</div></div>')
    P.append('</div>')

    for d in all_data:
        name = html.escape(d["name"])
        P.append('<div class="actor">')
        P.append(f'<h2>{name}</h2>')
        cov = (f'封面图 <b>{html.escape(d["cover_file"])}</b>'
               if d["cover_file"] else '<span class="no">缺封面图</span>')
        P.append(f'<div class="meta">CSV 数据源 <b>{d["csv_total"]}</b> 条 · '
                 f'已抓 xhtml <b>{d["xhtml"]}</b> · '
                 f'epub <b>{len(d["books"])}</b> 本 / {human(d["epub_size"])} · {cov}</div>')

        # 抓取进度
        if d["csv_total"]:
            sub = next((v for k, v in d["csv_actor_split"].items() if k == "单人"),
                       d["csv_total"])
            target = sub if d["xhtml"] <= sub else d["csv_total"]
            pct = d["xhtml"] / target * 100 if target else 0
            P.append(bar(pct))
            P.append(f'<div class="meta">抓取进度 <b>{d["xhtml"]}</b> / {target} '
                     f'（{pct:.0f}%）</div>')

        # 分组 / 年份
        g = d["groups"]
        if g:
            P.append('<div>')
            for k in CAT_ORDER + [x for x in g if x not in CAT_ORDER]:
                if g.get(k):
                    P.append(f'<span class="tag">{html.escape(k)} {g[k]}</span>')
            P.append('</div>')

        # epub 列表
        books = d["books"]
        if books:
            full = f'{d["name"]}作品集.epub'
            vols = [b for b in books if b["file"] != full]
            P.append('<table><tr><th>书</th><th class="num">部数</th>'
                     '<th class="num">体积</th><th>作者</th><th>排序作者</th>'
                     '<th>封面</th></tr>')
            for b in sorted(books, key=lambda x: x["file"] != full):
                star = " ★" if b["file"] == full else ""
                P.append(
                    f'<tr><td>{html.escape(b["file"][:-5])}{star}</td>'
                    f'<td class="num">{b["works"]}</td>'
                    f'<td class="num">{human(b["size"])}</td>'
                    f'<td>{html.escape(b["author"])}</td>'
                    f'<td>{html.escape(b["sort"])}</td>'
                    f'<td class="{"ok" if b["cover"] else "no"}">'
                    f'{"✓" if b["cover"] else "✗"}</td></tr>')
            P.append('</table>')
            vs = sum(b["works"] for b in vols)
            fw = next((b["works"] for b in books if b["file"] == full), 0)
            flag = ' class="ok">✓ 一致' if vs == fw else ' class="no">✗ 不符'
            P.append(f'<div class="meta">分卷合计 <b>{vs}</b> · 大全集 <b>{fw}</b> '
                     f'<span{flag}</span></div>')
            # 遗漏预警：xhtml 文稿数 > 大全集部数，说明有新抓的还没进书
            if d["xhtml"] > fw:
                P.append(f'<div class="meta"><span class="no">⚠ 遗漏预警：'
                         f'xhtml 有 <b>{d["xhtml"]}</b> 个，大全集只收了 '
                         f'<b>{fw}</b> 部，差 <b>{d["xhtml"] - fw}</b> 部'
                         f'（可能仍在抓取，抓完需重建 epub）</span></div>')
        else:
            P.append('<div class="meta">尚未生成 epub</div>')

        # CSV 清单（始终显示，不管有几个）
        if d["csv_files"]:
            P.append('<details><summary>CSV 数据源文件'
                     f'（{len(d["csv_files"])} 个）</summary><table>')
            for f, n in d["csv_files"]:
                star = " ★" if f == f'{d["name"]}作品集.csv' else ""
                P.append(f'<tr><td>{html.escape(f)}{star}</td>'
                         f'<td class="num">{n} 条</td></tr>')
            P.append('</table></details>')
        P.append('</div>')

    P.append('<div class="foot">★ = 大全集 · 部数来自 EPUB 目录（nav.xhtml）· '
             '体积为文件实际大小</div>')
    P.append('</body></html>')

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("".join(P))
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Life/成人图书创建")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = os.path.expanduser(args.root)
    out = args.out or os.path.join(root, "_数据看板.html")

    # 只认「有 {演员名}作品集.csv」的目录 —— 自动排除历史版本流程、文章等非演员目录
    actors = sorted(d for d in os.listdir(root)
                    if os.path.isdir(os.path.join(root, d))
                    and not d.startswith((".", "_"))
                    and os.path.exists(os.path.join(root, d, f"{d}作品集.csv")))
    all_data = []
    for a in actors:
        try:
            all_data.append(scan_actor(os.path.join(root, a), a))
            print(f"  扫描 {a} …")
        except Exception as e:
            print(f"  ! {a} 扫描失败: {e}")
    p = build_html(all_data, out)
    print(f"\n看板已生成: {p}")
    print(f"演员 {len(all_data)} 位 / epub {sum(len(d['books']) for d in all_data)} 本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
