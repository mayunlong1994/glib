"""GLIB · run —— 把 questions.md 里每道题单轮发给每个模型,存到 responses/。

用法:
  1. 把 OpenRouter key 放进 openrouter.txt(或设环境变量 OPENROUTER_API_KEY)
  2. 编辑 questions.md(一题一段,空行分隔,开头编号会被忽略)
  3. py -X utf8 run.py
"""
import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QFILE = ROOT / "questions.md"
OUTDIR = ROOT / "responses"

# ==== 在这里改你要对比的模型(OpenRouter slug)====
MODELS = {
    "gemini":   "google/gemini-3.5-flash",
    "gpt":      "openai/gpt-5.5",
    "sonnet":   "anthropic/claude-sonnet-4.6",
    "deepseek": "deepseek/deepseek-v4-flash",
}

MAX_TOKENS = 4000
WORKERS = 6
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k.strip()
    f = ROOT / "openrouter.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip().strip("\r\n")
    sys.exit("缺 key:设环境变量 OPENROUTER_API_KEY,或把 key 放进本目录的 openrouter.txt")


def parse_questions(path):
    """一题一段(空行分隔);开头的 'N. ' 编号会被自动剥掉。"""
    qs = []
    for b in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        b = b.strip()
        if not b or b.startswith("#"):
            continue
        b = re.sub(r"^\s*\d+\.\s*", "", b, count=1)
        if b:
            qs.append(b)
    return qs


def chat(key, model, content, retries=2):
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": content}],
                       "max_tokens": MAX_TOKENS}).encode()
    last = None
    for a in range(retries + 1):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                         headers={"Authorization": f"Bearer {key}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            time.sleep(2 * (a + 1))
    raise last


def main():
    key = load_key()
    qs = parse_questions(QFILE)
    if not qs:
        sys.exit(f"{QFILE} 里没解析到问题")
    OUTDIR.mkdir(exist_ok=True)
    jobs = [(i, q, mk, slug) for i, q in enumerate(qs, 1) for mk, slug in MODELS.items()]
    print(f"{len(qs)} 题 x {len(MODELS)} 模型 = {len(jobs)} 次调用", file=sys.stderr)

    results = defaultdict(list)
    costs = defaultdict(float)
    done = [0]

    def run(j):
        i, q, mk, slug = j
        try:
            r = chat(key, slug, q)
            ch = r["choices"][0]
            return (mk, i, q, ch["message"].get("content") or "",
                    ch.get("finish_reason"), (r.get("usage") or {}).get("cost", 0) or 0, None)
        except Exception as e:
            return (mk, i, q, "", None, 0, str(e))

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for f in as_completed([ex.submit(run, j) for j in jobs]):
            mk, i, q, c, fin, cost, err = f.result()
            results[mk].append({"id": i, "q": q, "content": c, "finish_reason": fin, "error": err})
            costs[mk] += cost
            done[0] += 1
            if done[0] % 40 == 0:
                print(f"  {done[0]}/{len(jobs)}", file=sys.stderr)

    for mk in MODELS:
        rows = sorted(results[mk], key=lambda r: r["id"])
        (OUTDIR / f"{mk}.json").write_text(
            json.dumps({"model_key": mk, "model_slug": MODELS[mk],
                        "total_cost": round(costs[mk], 4), "turns": rows},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        errs = sum(1 for r in rows if r["error"])
        print(f"{mk}: {len(rows)} 答案, {errs} 错误, ${costs[mk]:.4f}", file=sys.stderr)
    print(f"总计 ${sum(costs.values()):.4f}  ->  {OUTDIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
