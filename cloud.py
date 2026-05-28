"""GLIB · cloud —— 给每个模型画一张"性格词云"。

字号 = 频次 x log(独特度),并按文档频率过滤一次性内容词,只留各家真正的腔调签名。
中文需要 CJK 字体:默认找 Windows 黑体,其他系统用环境变量 GLIB_FONT 指定 .ttf/.ttc。

用法: py -X utf8 cloud.py
"""
import json
import math
import os
import random as _random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import jieba
import numpy as np
from wordcloud import WordCloud

ROOT = Path(__file__).resolve().parent
RUNDIR = ROOT / "responses"
OUTDIR = ROOT / "clouds"

FONT = os.environ.get("GLIB_FONT") or "C:/Windows/Fonts/simhei.ttf"

# 每个模型一个基础色相 -> 云内同色系、柔和有别
BASE_HUE = {"gemini": 205, "gpt": 145, "sonnet": 280, "deepseek": 25}

HAN = re.compile(r"[一-鿿]")
STOP = set("""
的 了 和 是 在 我 你 他 她 它 们 这 那 有 也 都 就 不 人 你的 我的 一个 一种 这个 那个
什么 怎么 可以 这样 那样 因为 所以 但是 如果 而且 或者 然后 还是 已经 一些 这些 那些
没有 不是 就是 这种 那种 一下 比如 而是 并且 不会 不能 自己 我们 你们 他们 一直 这里
那里 现在 时候 一样 真的 觉得 知道 这么 那么 其实 应该 可能 因此 于是 也许 等等 通过
对于 关于 当然 至于 以及 同时 此外 另外 总之 首先 其次 最后 一点 这是 不要 需要 一会
还有 只是 而已 之类 一般 比较 越来越 这件 那件 一件 事情 东西 方面 部分 问题 情况
就是说 也就是 所谓 一旦 不过 反正 毕竟 既然 无论 不管 哪怕 哪些 哪个 多少 几个 这次
能 会 要 想 用 做 如何 它会 他会 这部分 一类
""".split())


def ellipse_mask(w=1200, h=820, pad=60):
    rx, ry = w / 2 - pad, h / 2 - pad
    y, x = np.ogrid[:h, :w]
    mask = 255 * np.ones((h, w), dtype=np.uint8)
    mask[((x - w / 2) / rx) ** 2 + ((y - h / 2) / ry) ** 2 <= 1] = 0
    return mask


def make_color_func(base_hue):
    def f(word, font_size, position, orientation, random_state=None, **kw):
        rs = random_state or _random.Random()
        hue = (base_hue + rs.randint(-16, 16)) % 360
        return f"hsl({hue}, {rs.randint(42, 60)}%, {rs.randint(32, 50)}%)"
    return f


def tokenize(text):
    for w in jieba.cut(text):
        w = w.strip()
        if len(w) < 2 or not HAN.search(w) or w in STOP or any(c.isspace() for c in w):
            continue
        yield w


def main():
    if not Path(FONT).exists():
        sys.exit(f"找不到中文字体: {FONT}\n用环境变量 GLIB_FONT 指定一个 .ttf/.ttc CJK 字体路径")
    files = sorted(RUNDIR.glob("*.json"))
    if not files:
        sys.exit(f"{RUNDIR} 里没有结果,先跑 run.py")
    OUTDIR.mkdir(exist_ok=True)

    by_model = defaultdict(Counter)   # 总词频
    by_df = defaultdict(Counter)      # 文档频率(出现在多少道答案里)
    for fp in files:
        d = json.loads(fp.read_text(encoding="utf-8"))
        mk = d["model_key"]
        for t in d["turns"]:
            words = list(tokenize(t.get("content") or ""))
            for w in words:
                by_model[mk][w] += 1
            for w in set(words):
                by_df[mk][w] += 1

    models = sorted(by_model)
    totals = {m: sum(by_model[m].values()) for m in models}

    LIFT_MIN, MIN_COUNT, MIN_DF = 1.3, 4, 4
    for m in models:
        others, o_total = Counter(), 0
        for x in models:
            if x != m:
                others.update(by_model[x])
                o_total += totals[x]
        raw = {}
        for w, c in by_model[m].items():
            if c < MIN_COUNT or by_df[m].get(w, 0) < MIN_DF:
                continue
            lift = (c / max(1, totals[m]) + 1e-9) / (others.get(w, 0) / max(1, o_total) + 1e-9)
            if lift >= LIFT_MIN:
                raw[w] = c * math.log(lift)
        if not raw:
            print(f"{m}: 没有签名词?", file=sys.stderr)
            continue
        freqs = {w: v ** 0.6 for w, v in raw.items()}   # 幂压缩,最大词别太夸张
        wc = WordCloud(font_path=FONT, background_color="white",
                       mask=ellipse_mask(1200, 820, pad=60),
                       max_words=40, prefer_horizontal=1.0, margin=14,
                       min_font_size=14, max_font_size=150, relative_scaling=0.5,
                       color_func=make_color_func(BASE_HUE.get(m, 205)))
        wc.generate_from_frequencies(freqs)
        out = OUTDIR / f"cloud_{m}.png"
        wc.to_file(str(out))
        top = [w for w, _ in sorted(freqs.items(), key=lambda x: -x[1])[:8]]
        print(f"{m}: {len(freqs)} 词 -> {out.name} | top: {top}", file=sys.stderr)


if __name__ == "__main__":
    main()
