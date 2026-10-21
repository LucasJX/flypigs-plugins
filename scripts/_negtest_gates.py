#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反向测试：确认新加的校验闸门**真的会红**。

只加断言不验证判据 = 假绿。做法：原地篡改 → 跑 validator → 断言退出码非 0 →
finally 里按字节还原原文件（并断言还原成功）。

覆盖的闸门：
  1. index.json.features_count 与 manifest 不一致
  2. legacy_label 的 fn_kind 在 memory 与 manifest 之间不一致（RA2「钱」的历史 bug）
  3. manifest.features_count 与主功能数不一致
  4. 事件类型铁律：fn_kind 与引擎 On*Event 分派不符（RA2「钱」曾被写成 button）
  5. 可逆 mod 铁律：code_inject / code_patch 被声明成一次性 button（JC3 3 项）
  6. 权威中文名：功能名与 char_table.h 的文案不符
  7. 权威分组：分组与 main.js CATEGORY_OF 不符（AdjustGameSpeed 曾独占「任务调速」组）
  8. 输入型铁律：input 功能预填 target_value（「钱」的金额输入框必须初始留空）

用法：python scripts/_negtest_gates.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run_validator() -> tuple[int, str]:
    p = subprocess.run(
        [PY, str(ROOT / "scripts" / "plugins-validate.py"), "--root", str(ROOT), "--strict", "--quiet"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def case(name: str, path: Path, mutate, expect_fail: bool = True) -> bool:
    orig = path.read_bytes()
    try:
        text = orig.decode("utf-8")
        new = mutate(text)
        if new == text:
            print(f"[FAIL] {name}: 变异没有生效（正则没匹配到），测试本身失效")
            return False
        path.write_bytes(new.encode("utf-8"))
        code, out = run_validator()
        ok = (code != 0) if expect_fail else (code == 0)
        tail = "\n".join(
            l for l in out.splitlines()
            if "ERROR" in l or "features_count" in l or "fn_kind" in l
            or "中文名" in l or "分组" in l or "target_value" in l
        )
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: exit={code} (期望 {'非0' if expect_fail else '0'})")
        if tail:
            for l in tail.splitlines()[:4]:
                print(f"        {l}")
        return ok
    finally:
        path.write_bytes(orig)
        back = path.read_bytes()
        assert back == orig, f"还原失败: {path}"


def main() -> int:
    results = []
    ra2_mf = ROOT / "plugins" / "ra2_yr" / "manifest.json"
    ra2_mem = ROOT / "plugins" / "ra2_yr" / "memory.json"
    jc3_mf = ROOT / "plugins" / "just_cause_3" / "manifest.json"

    # 1) index.json.features_count 与 manifest 不一致 —— 曾经的「市场卡片 31 项 vs 详情页 32 项」
    results.append(case(
        "index.features_count 被篡改 (32 -> 99)",
        ROOT / "index.json",
        lambda t: t.replace('"features_count": 32', '"features_count": 99'),
    ))

    # 2) legacy_label 插件的 fn_kind 在 memory 与 manifest 之间不一致 —— RA2「钱」的历史 bug
    results.append(case(
        "RA2 apply 的 fn_kind 改回 button（复现原 bug）",
        ra2_mf,
        lambda t: re.sub(
            r'("id": "apply",[\s\S]*?"type": )"input"(,[\s\S]*?"fn_kind": )"input"',
            r'\1"button"\2"button"',
            t, count=1),
    ))

    # 3) manifest.features_count 与主功能数不一致
    results.append(case(
        "manifest.features_count 被篡改 (32 -> 5)",
        ra2_mf,
        lambda t: t.replace('"features_count": 32', '"features_count": 5'),
    ))

    # 4) 事件类型铁律：只改 memory 侧的 fn_kind（manifest 不动）——
    #    两边一致但都写错的情况也要被抓住（这正是「照 model.h 注释改」造成的那类错）
    results.append(case(
        "RA2 apply 在 memory+manifest 两侧同时写成 checkbox（与引擎 input 事件不符）",
        ra2_mem,
        lambda t: re.sub(
            r'("id": "apply",[\s\S]*?"fn_kind": )"input"',
            r'\1"checkbox"',
            t, count=1),
    ))

    # 5) 可逆 mod 铁律：JC3 的 code_inject 被声明成一次性 button（开了就关不掉）
    results.append(case(
        "JC3 easy_clear_heat 改回 button（code_inject 可逆，必须是开关）",
        jc3_mf,
        lambda t: re.sub(
            r'("id": "easy_clear_heat",[\s\S]*?"type": )"checkbox"(,[\s\S]*?"fn_kind": )"checkbox"',
            r'\1"button"\2"button"',
            t, count=1),
    ))

    # 6) 权威中文名：功能名被改成自造叫法
    results.append(case(
        "RA2 god 的中文名改成 '上帝模式'（权威文案是 '无敌'）",
        ra2_mem,
        lambda t: re.sub(
            r'("id": "god",[\s\S]*?"name": )"无敌"',
            r'\1"上帝模式"',
            t, count=1),
    ))

    # 7) 权威分组：AdjustGameSpeed 被挪回独占的「任务调速」组
    results.append(case(
        "RA2 adjust_game_speed 改回独立分组 '任务调速'（权威分组是 '战场控制'）",
        ra2_mem,
        lambda t: re.sub(
            r'("id": "adjust_game_speed",[\s\S]*?"group": )"战场控制"',
            r'\1"任务调速"',
            t, count=1),
    ))

    # 8) 输入型功能不得预填 target_value —— 「钱」的金额输入框必须初始留空，
    #    预填的数会被用户误当成「要的钱」，而且客户端 enable 路径会把它直接下发。
    results.append(case(
        "RA2 apply 预填 target_value=23333（金额输入框必须初始留空）",
        ra2_mem,
        lambda t: re.sub(
            r'("id": "apply",[\s\S]*?"fn_kind": "input",)',
            r'\1\n      "target_value": 23333,',
            t, count=1),
    ))

    # 9) 篡改后必须恢复原状（防止上面几个 case 互相污染）
    code, _ = run_validator()
    ok = code == 0
    print(f"[{'PASS' if ok else 'FAIL'}] 还原后 validator 恢复全绿: exit={code} (期望 0)")
    results.append(ok)

    print()
    print(f"反向测试：{sum(1 for r in results if r)}/{len(results)} 通过")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
