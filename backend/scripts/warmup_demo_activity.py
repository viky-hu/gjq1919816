# -*- coding: utf-8 -*-
"""演示预热：用各账号的真实语料自动提问，让宏观面板有数据。

为什么需要
----------
宏观窗口的左下（D2 检索热度榜）和右上（D4 节点贡献曲线）都是
**按 QueryLog 的时间窗口统计**，不是统计文件：

    today / week / month  <-- 窗口起点在最近

而库里现有的查询日志都在 2026-08-23 ~ 09-02，距今已一个多月，
所以这两个面板始终是空白（连带 D3 沙盘的 activity 也全是 0）。

**载入文件不会让它们有数据** —— 文件只影响 D1 时间线与 D5 词云。

本脚本通过对系统**真实提问**来产生查询记录：每个账号问 2~3 个它自己语料
答得上来的问题。这些记录是真实的（答案由系统实际生成），不是伪造的活动数据；
演示时打开面板即可看到数据，也经得起追问。

用法
----
    # 先确认后端在跑（默认 6006）
    python scripts/warmup_demo_activity.py

    # 指定后端地址 / 只预热某几个账号 / 只看不写
    python scripts/warmup_demo_activity.py --base http://127.0.0.1:6006
    python scripts/warmup_demo_activity.py --only admin 法学教研室
    python scripts/warmup_demo_activity.py --dry-run

前置：后端已启动、.env 里的 key 有效（提问要调 LLM 与嵌入）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 账号 / 密码（与 seed_nodes.py 一致）
ACCOUNTS = {
    "admin": "admin123456",
    "大数据教研室": "123456",
    "马克思理论教研室": "123456",
    "法学教研室": "123456",
    "图书馆": "123456",
    "语言实践中心": "123456",
}

# 每个账号的问题，**按其实际入库的文档来定**，保证答得上、答案有意义
QUESTIONS = {
    # 民法典 + 婚姻家庭编解释一 + 时间效力规定 + 物权编解释一 + 继承编解释一
    "admin": [
        "民法典中关于抵押权的规定是什么？",
        "法定继承的顺序是怎样的？",
        "不动产物权的设立和变动什么时候发生效力？",
    ],
    # 公司法 + 担保制度解释
    "大数据教研室": [
        "设立有限责任公司需要满足哪些条件？",
        "保证担保的范围包括哪些内容？",
    ],
    # 侵权责任编解释一 + 总则编解释
    "马克思理论教研室": [
        "侵权责任的构成要件有哪些？",
        "民事法律行为在什么情况下无效？",
    ],
    # 刑法 + 刑事诉讼法 + 民事案件案由规定
    "法学教研室": [
        "刑法中关于盗窃罪是怎么规定的？",
        "取保候审的适用条件是什么？",
    ],
    # 劳动争议解释一 / 二
    "图书馆": [
        "劳动争议案件的受案范围包括哪些？",
        "加班费应当如何计算？",
    ],
    # 彩礼规定
    "语言实践中心": [
        "彩礼返还的条件是什么？",
        "彩礼返还的诉讼时效如何认定？",
    ],
}


def post(base: str, path: str, body: dict, token: str | None = None,
         timeout: int = 900):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), time.time() - t0
    except Exception as e:
        return None, "{0}: {1}".format(type(e).__name__, str(e)[:160]), time.time() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description="演示预热：产生真实的查询活动")
    ap.add_argument("--base", default="http://127.0.0.1:6006", help="后端地址")
    ap.add_argument("--only", nargs="*", default=None, help="只预热指定账号")
    ap.add_argument("--dry-run", action="store_true", help="只列出要问什么，不实际提问")
    ap.add_argument("--timeout", type=int, default=900, help="单次提问超时（秒）")
    args = ap.parse_args()

    accounts = args.only or list(ACCOUNTS)

    print("=" * 78)
    print("演示预热：让宏观面板产生真实活动数据")
    print("=" * 78)
    print("后端:", args.base)
    print("账号:", "、".join(accounts))
    total_q = sum(len(QUESTIONS.get(a, [])) for a in accounts)
    print("将提问: {0} 个问题".format(total_q))
    if args.dry_run:
        print()
        for a in accounts:
            print("  [{0}]".format(a))
            for q in QUESTIONS.get(a, []):
                print("     {0}".format(q))
        print()
        print("[dry-run] 未实际提问。")
        return

    print()

    summary = []
    for acct in accounts:
        pwd = ACCOUNTS.get(acct)
        if not pwd:
            print("  [跳过] 未知账号 {0}".format(acct))
            continue

        print("-" * 78)
        print("账号：{0}".format(acct))
        print("-" * 78)

        s, b, _ = post(args.base, "/api/auth/login",
                       {"username": acct, "password": pwd})
        if s != 200:
            print("  [!!] 登录失败 HTTP {0}  {1}".format(s, b[:120]))
            summary.append((acct, 0, 0, "登录失败"))
            continue
        token = json.loads(b)["access_token"]
        print("  登录 OK")

        ok = fail = 0
        for q in QUESTIONS.get(acct, []):
            s2, b2, t2 = post(args.base, "/api/query/",
                              {"question": q, "mode": "mix"},
                              token=token, timeout=args.timeout)
            if s2 == 200:
                try:
                    d = json.loads(b2)
                    ans = str(d.get("answer", ""))
                    ev = d.get("evidence") or []
                    flag = "OK" if len(ans) > 30 else "空答"
                    if len(ans) > 30:
                        ok += 1
                    else:
                        fail += 1
                    print("    [{0}] {1:.0f}s  answer {2} 字  evidence {3} 条  | {4}".format(
                        flag, t2, len(ans), len(ev), q[:30]))
                except Exception:
                    fail += 1
                    print("    [!!] 解析失败  {0}".format(q[:30]))
            else:
                fail += 1
                print("    [!!] HTTP {0}  {1}  | {2}".format(
                    s2, str(b2)[:90], q[:30]))
        summary.append((acct, ok, fail, ""))

    # ── 汇总 ──
    print()
    print("=" * 78)
    print("汇总")
    print("=" * 78)
    print("  {0:<18} {1:>6} {2:>6}".format("账号", "成功", "失败"))
    tot_ok = tot_fail = 0
    for acct, ok, fail, err in summary:
        tot_ok += ok
        tot_fail += fail
        suffix = "  ({0})".format(err) if err else ""
        print("  {0:<18} {1:>6} {2:>6}{3}".format(acct, ok, fail, suffix))
    print("  {0:<18} {1:>6} {2:>6}".format("合计", tot_ok, tot_fail))

    print()
    if tot_ok:
        print("已产生 {0} 条真实查询记录（时间为今天）。".format(tot_ok))
        print("现在打开宏观窗口：")
        print("  左下 检索热度榜  —— 会显示各账号今日/本周的提问次数")
        print("  右上 贡献曲线    —— 会显示各账号的贡献趋势")
        print("  D3 三维沙盘      —— 各节点 activity 不再为 0")
    else:
        print("没有成功的提问。请确认后端在跑、.env 里的 key 有效。")
        print("提示：若报 embedding / LLM 相关错误，多为网络或额度问题。")
    print()
    print("说明：这些记录是**系统实际生成的**，不是伪造的活动数据；")
    print("      演示时若被问到数据来源，可以直接答『演示前跑了一批真实问答』。")


if __name__ == "__main__":
    main()
