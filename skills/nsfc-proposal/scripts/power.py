#!/usr/bin/env python3
"""样本量与最小可检测效应（正态近似，只用标准库）。

用法：
  power.py props --p0 P0 --p1 P1 [--alpha 0.05] [--power 0.8] [--cluster-size M --icc ICC] [--r R]
  power.py props-mde --p0 P0 (--n N | --clusters K --cluster-size M --icc ICC) [--lower] [--r R] [--alpha] [--power]
  power.py means --d D [--ratio K] [--alpha] [--power] [--cluster-size M --icc ICC]
  power.py means-mde --n1 N1 --n2 N2 [--alpha] [--power] [--cluster-size M --icc ICC]
加 --json 输出机器可读结果。

设计与子命令：两比例个体随机用 props；样本量已定、求最小可检测比例用 props-mde --n（结局预期下降加 --lower）；
整群随机加 --cluster-size 与 --icc（props-mde 用 --clusters）。两均值用 means；样本量已定用 means-mde。
层级回归的 f² 检验力不在本脚本范围内。

退出码：0 完成；2 参数越界或缺失。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from statistics import NormalDist
from typing import Any, Sequence

EXIT_OK, EXIT_USAGE = 0, 2
MDE_STEP = 0.001
SMALL_N = 10  # means 每组不足 10 人时每组加 1 人，与精确 t 检验一致
NORMAL = NormalDist()


class ArgError(ValueError):
    """参数越界或缺失。"""


def _z(alpha: float, power: float) -> tuple[float, float]:
    return NORMAL.inv_cdf(1 - alpha / 2), NORMAL.inv_cdf(power)


def _check_common(args: argparse.Namespace) -> None:
    if not 0 < args.alpha < 1:
        raise ArgError("--alpha 须在 0 到 1 之间（不含端点）")
    if not 0 < args.power < 1:
        raise ArgError("--power 须在 0 到 1 之间（不含端点）")
    size, icc = getattr(args, "cluster_size", None), getattr(args, "icc", None)
    if (size is None) != (icc is None):
        raise ArgError("整群设计须同时给 --cluster-size 和 --icc")
    if size is not None and size < 1:
        raise ArgError("--cluster-size 须为不小于 1 的整数")
    if icc is not None and not 0 <= icc < 1:
        raise ArgError("--icc 须在 0 到 1 之间（含 0，不含 1）")
    r = getattr(args, "r", 0.0)
    if not 0 <= r < 1:
        raise ArgError("--r 须在 0 到 1 之间（含 0，不含 1）")


def design_effect(size: int | None, icc: float | None) -> float:
    return 1.0 if size is None or icc is None else 1 + (size - 1) * icc


def props_n(p0: float, p1: float, alpha: float, power: float) -> float:
    """两比例每组人数（未取整）。"""
    za, zb = _z(alpha, power)
    pbar = (p0 + p1) / 2
    top = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))
    return top ** 2 / (p1 - p0) ** 2


def _clusters(n: int, size: int) -> int:
    return math.ceil(n / size - 1e-9)


def _adjust(n_raw: float, size: int | None, icc: float | None, r: float) -> dict[str, Any]:
    de = design_effect(size, icc)
    n = math.ceil(math.ceil(n_raw - 1e-9) * de * (1 - r * r) - 1e-9)  # 先取整成单人群样本量，再乘设计效应
    out: dict[str, Any] = {"design_effect": de, "n_per_group": n}
    if size is not None:
        out["clusters_per_group"] = _clusters(n, size)
    return out


def calc_props(p0: float, p1: float, alpha: float, power: float, size: int | None, icc: float | None,
               r: float) -> dict[str, Any]:
    raw = props_n(p0, p1, alpha, power)
    return {"n_unadjusted": math.ceil(raw - 1e-9), **_adjust(raw, size, icc, r)}


def calc_props_mde(p0: float, alpha: float, power: float, r: float, *, n: int | None = None,
                   clusters: int | None = None, size: int | None = None, icc: float | None = None,
                   lower: bool = False) -> dict[str, Any]:
    """按 0.001 步长离开 p0，找所需人数（或群数）不超过给定值的第一个 p1。给 n 为个体随机，给 clusters 为整群。"""
    sign = -1 if lower else 1
    steps = int(round((p0 if lower else 1 - p0) / MDE_STEP))
    for i in range(1, steps):
        p1 = round(p0 + sign * i * MDE_STEP, 3)
        if not 0 < p1 < 1:
            break
        result = calc_props(p0, p1, alpha, power, size, icc, r)
        enough = result["clusters_per_group"] <= clusters if clusters is not None else result["n_per_group"] <= (n or 0)
        if enough:
            out = {"p1": p1, "difference_pp": round((p1 - p0) * 100, 1), "n_per_group": result["n_per_group"],
                   "design_effect": result["design_effect"]}
            if clusters is not None:
                out["clusters_needed"] = result["clusters_per_group"]
            return out
    side, edge = ("之下", "大于 0") if lower else ("之上", "小于 1")
    budget = f"每组 {clusters} 个群" if clusters is not None else f"每组 {n} 人"
    raise ArgError(f"{budget}，在 p0={p0} {side}找不到可检测的 p1（{edge}）")


def calc_means(d: float, ratio: float, alpha: float, power: float, size: int | None, icc: float | None) -> dict[str, Any]:
    za, zb = _z(alpha, power)
    n1_raw = (1 + 1 / ratio) * ((za + zb) / d) ** 2 + za ** 2 / 4
    out = _adjust(n1_raw, size, icc, 0.0)
    n1 = out["n_per_group"]
    n2 = math.ceil(n1 * ratio - 1e-9)
    added = 1 if min(n1, n2) < SMALL_N else 0
    n1, n2 = n1 + added, n2 + added
    out.update({"n_per_group": n1, "n_group2": n2, "n_total": n1 + n2, "ratio": ratio, "small_sample_added": added})
    if size is not None:
        out.update({"clusters_per_group": _clusters(n1, size), "clusters_group2": _clusters(n2, size)})
    return out


def calc_means_mde(n1: int, n2: int, alpha: float, power: float, size: int | None = None,
                   icc: float | None = None) -> dict[str, Any]:
    za, zb = _z(alpha, power)
    adj = za ** 2 / 4
    de = design_effect(size, icc)
    e1, e2 = n1 / de, n2 / de  # 有效样本量
    k = e2 / e1  # 与 means 互逆：n1 = (1+1/k)((za+zb)/d)^2 + za^2/4
    d = (za + zb) * math.sqrt((1 + 1 / k) / (e1 - adj)) if e1 > adj else float("nan")
    return {"d": d, "design_effect": de, "n1_effective": round(e1, 1), "n2_effective": round(e2, 1),
            "small_sample_caveat": min(e1, e2) < SMALL_N}


# ---------------------------------------------------------------- 命令行

def _say(args: argparse.Namespace, data: dict[str, Any], lines: Sequence[str]) -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    else:
        print("\n".join(lines))


def _cluster_note(data: dict[str, Any]) -> list[str]:
    if "clusters_per_group" not in data:
        return []
    head = f"整群设计：设计效应 DE = 1 + (M−1)·ICC = {data['design_effect']:.2f}，"
    if data.get("clusters_group2", data["clusters_per_group"]) != data["clusters_per_group"]:
        return [head + f"第一组需 {data['clusters_per_group']} 个群，第二组需 {data['clusters_group2']} 个群。"]
    return [head + f"每组需 {data['clusters_per_group']} 个群。"]


def _cmd_props(args: argparse.Namespace) -> None:
    _check_common(args)
    for name in ("p0", "p1"):
        if not 0 < getattr(args, name) < 1:
            raise ArgError(f"--{name} 须在 0 到 1 之间（不含端点）")
    if args.p0 == args.p1:
        raise ArgError("--p0 与 --p1 不能相等")
    data = calc_props(args.p0, args.p1, args.alpha, args.power, args.cluster_size, args.icc, args.r)
    lines = [f"两比例比较（{args.p0} 对 {args.p1}，α={args.alpha}，把握度 {args.power}）：每组需 {data['n_per_group']} 人。",
             "公式：n = (zα·√(2p̄q̄) + zβ·√(p0q0+p1q1))² / (p1−p0)²；整群时 n·DE·(1−R²)，群数 = ⌈n/M⌉。"]
    _say(args, data, lines + _cluster_note(data))


def _check_mde_design(args: argparse.Namespace) -> None:
    """--n 与 --clusters（连同 --cluster-size、--icc）恰好给一种。"""
    cluster_given = args.clusters is not None or args.cluster_size is not None or args.icc is not None
    if args.n is not None and cluster_given:
        raise ArgError("--n 用于个体随机设计，不与 --clusters、--cluster-size、--icc 同用")
    if args.n is None and args.clusters is None:
        raise ArgError("props-mde 须给 --n（个体随机，每组人数）或 --clusters 加 --cluster-size 与 --icc（整群）")
    if args.n is not None and args.n < 2:
        raise ArgError("--n 须为不小于 2 的整数")
    if args.clusters is not None:
        if args.clusters < 1:
            raise ArgError("--clusters 须为不小于 1 的整数")
        if args.cluster_size is None:
            raise ArgError("整群设计须同时给 --clusters、--cluster-size 和 --icc")


def _cmd_props_mde(args: argparse.Namespace) -> None:
    _check_common(args)
    if not 0 < args.p0 < 1:
        raise ArgError("--p0 须在 0 到 1 之间（不含端点）")
    _check_mde_design(args)
    data = calc_props_mde(args.p0, args.alpha, args.power, args.r, n=args.n, clusters=args.clusters,
                          size=args.cluster_size, icc=args.icc, lower=args.lower)
    side, best = ("低", "最大") if args.lower else ("高", "最小")
    gap = abs(data["difference_pp"])
    if args.clusters is not None:
        budget = f"每组 {args.clusters} 个群（每群 {args.cluster_size} 人，ICC={args.icc}）"
        rule = f"所需群数 ⌈n·DE·(1−R²)/M⌉ 不超过 {args.clusters}"
    else:
        budget, rule = f"每组 {args.n} 人", f"所需每组人数 n·(1−R²) 不超过 {args.n}"
    _say(args, data, [f"{budget}：可检测的 p1 = {data['p1']}，比 p0 {side} {gap} 个百分点。",
                      f"公式：以 0.001 为步长，找{rule} 的{best} p1。"])


def _cmd_means(args: argparse.Namespace) -> None:
    _check_common(args)
    if not (math.isfinite(args.d) and args.d > 0):
        raise ArgError("--d 须为大于 0 的有限数")
    if not (math.isfinite(args.ratio) and args.ratio > 0):
        raise ArgError("--ratio 须为大于 0 的有限数")
    data = calc_means(args.d, args.ratio, args.alpha, args.power, args.cluster_size, args.icc)
    lines = [f"两样本均值比较（d={args.d}，α={args.alpha}，把握度 {args.power}）：每组需 {data['n_per_group']} 人"
             f"（第二组 {data['n_group2']} 人，共 {data['n_total']} 人）。",
             "公式：n1 = (1+1/k)·((zα+zβ)/d)² + zα²/4（正态近似加 Guenther 修正）；整群时乘 DE。"]
    if data["small_sample_added"]:
        lines.append(f"每组算得不足 {SMALL_N} 人：每组加 1 人，与精确 t 检验的结果一致。")
    _say(args, data, lines + _cluster_note(data))


def _cmd_means_mde(args: argparse.Namespace) -> None:
    _check_common(args)
    if args.n1 < 2 or args.n2 < 2:
        raise ArgError("--n1、--n2 须不小于 2")
    data = calc_means_mde(args.n1, args.n2, args.alpha, args.power, args.cluster_size, args.icc)
    if math.isnan(data["d"]):
        raise ArgError("样本量太小，无法计算")
    data["d"] = round(data["d"], 4)
    lines = [f"两组 {args.n1} 与 {args.n2} 人：最小可检测效应 d ≈ {data['d']:.2f}。",
             "公式：d = (zα+zβ)·√((1+1/k)/(n1−zα²/4))，k = n2/n1；整群时 n1、n2 先除以 DE。"]
    if args.cluster_size is not None:
        lines.append(f"整群设计：DE = {data['design_effect']:.2f}，有效样本量 {data['n1_effective']} 与 {data['n2_effective']}。")
    if data["small_sample_caveat"]:
        label = "有效样本量" if args.cluster_size is not None else "每组人数"
        lines.append(f"{label}不足 {SMALL_N}：正态近似偏乐观，实际可检测的 d 更大。")
    _say(args, data, lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="样本量与最小可检测效应（标准库，正态近似）")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--alpha", type=float, default=0.05)
        p.add_argument("--power", type=float, default=0.8)
        p.add_argument("--json", action="store_true", help="输出 JSON")
        p.add_argument("--cluster-size", type=int, help="每群人数 M")
        p.add_argument("--icc", type=float, help="组内相关系数")

    props = sub.add_parser("props", help="两比例每组人数")
    props.add_argument("--p0", type=float, required=True)
    props.add_argument("--p1", type=float, required=True)
    props.add_argument("--r", type=float, default=0.0, help="协变量与结局的相关系数 R，样本量乘 (1−R²)（默认 0）")
    common(props)
    mde = sub.add_parser("props-mde", help="样本量已定时最小可检测的 p1（个体随机或整群）")
    mde.add_argument("--p0", type=float, required=True)
    mde.add_argument("--n", type=int, help="个体随机：每组人数 N")
    mde.add_argument("--clusters", type=int, help="整群：每组群数 K（同时给 --cluster-size 与 --icc）")
    mde.add_argument("--lower", action="store_true", help="在 p0 之下找 p1（结局预期下降）")
    mde.add_argument("--r", type=float, default=0.0, help="协变量与结局的相关系数 R")
    common(mde)
    means = sub.add_parser("means", help="两样本均值每组人数")
    means.add_argument("--d", type=float, required=True)
    means.add_argument("--ratio", type=float, default=1.0, help="第二组与第一组人数之比（默认 1）")
    common(means)
    meansmde = sub.add_parser("means-mde", help="已知每组人数时的最小可检测 d")
    meansmde.add_argument("--n1", type=int, required=True)
    meansmde.add_argument("--n2", type=int, required=True)
    common(meansmde)
    return parser


COMMANDS = {"props": _cmd_props, "props-mde": _cmd_props_mde, "means": _cmd_means, "means-mde": _cmd_means_mde}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except ArgError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
