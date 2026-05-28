"""GLIB · analyze —— 出数字版:各家原始高频 + 签名词(相对其他家的过度使用倍率)。

词云是给人看乐子的,这个是给你查证的。用法: py -X utf8 analyze.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path

import jieba

ROOT = Path(__file__).resolve().parent
RUNDIR = ROOT / "responses"
OUT = ROOT / "analysis.md"

HAN = re.compile(r"[一-鿿]")
STOP = set("""
的 了 和 是 在 我 你 他 她 它 们 这 那 有 也 都 就 不 人 你的 我的 一个 一种 这个 那个
什么 怎么 可以 这样 那样 因为 所以 但是 如果 而且 或者 然后 还是 已经 一些 这些 那些
没有 不是 就是 这种 那种 一下 比如 而是 并且 不会 不能 自己 我们 你们 他们 一直 这里
那里 现在 时候 一样 真的 觉得 知道 这么 那么 其实 应该 可能 因此 于是 也许 等等 通过
对于 关于 当然 至于 以及 同时 此外 另外 总之 首先 其次 最后 一点 这是 不要 需要 一会
还有 只是 而已 之类 一般 比较 越来越 事情 东西 方面 部分 问题 情况 能 会 要 想 用 做
""".split())


def tokenize(text):
    for w in jieba.cut(text):
        w = w.strip()
        if len(w) < 2 or not HAN.search(w) or w in STOP or any(c.isspace() for c in w):
            continue
        yield w


def main():
    files = sorted(RUNDIR.glob("*.json"))
    if not files:
        sys.exit(f"{RUNDIR} 里没有结果,先跑 run.py")
    by_model = defaultdict(Counter)
    by_df = defaultdict(Counter)
    chars = defaultdict(int)
    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        mk = d["model_key"]
        for t in d["turns"]:
            c = t.get("content") or ""
            chars[mk] += len(c)
            words = list(tokenize(c))
            for w in words:
                by_model[mk][w] += 1
            for w in set(words):
                by_df[mk][w] += 1

    models = sorted(by_model)
    totals = {m: sum(by_model[m].values()) for m in models}
    buf = StringIO()
    buf.write("# GLIB 分析\n\n| 模型 | 输出总字数 | 有效词数 |\n|---|---|---|\n")
    for m in models:
        buf.write(f"| {m} | {chars[m]:,} | {totals[m]:,} |\n")

    for m in models:
        buf.write(f"\n## {m} · 原始高频 top 25\n\n| 词 | 次 |\n|---|---|\n")
        for w, c in by_model[m].most_common(25):
            buf.write(f"| {w} | {c} |\n")

    for m in models:
        others, o_total = Counter(), 0
        for x in models:
            if x != m:
                others.update(by_model[x])
                o_total += totals[x]
        scored = []
        for w, c in by_model[m].items():
            if c < 4 or by_df[m].get(w, 0) < 4:
                continue
            lift = (c / max(1, totals[m]) + 1e-9) / (others.get(w, 0) / max(1, o_total) + 1e-9)
            scored.append((w, lift, c, others.get(w, 0)))
        scored.sort(key=lambda x: -x[1])
        buf.write(f"\n## {m} · 签名词(相对其他家的过度使用)top 25\n\n")
        buf.write("| 词 | 倍率 | 本家 | 其他家合计 |\n|---|---|---|---|\n")
        for w, lift, c, oc in scored[:25]:
            buf.write(f"| {w} | {lift:.1f}x | {c} | {oc} |\n")

    OUT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
