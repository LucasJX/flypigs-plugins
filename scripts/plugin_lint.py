#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plugin_lint.py — 插件 memory.json 语义校验（Plugin Spec v2.0）

在打包 / 发布前运行，把「数据错误」类问题在源头拦截。
这类问题过去只会在游戏运行时暴露（AOB not found / 游戏卡死闪退），现在提前到打包时。

校验项（均来自 JC3 实踩的坑，逐条对应规范 §2.3 / §6）：
  A. memory.json 不含 UTF-8 BOM（严格 JSON 解析器会失败）
  B. 每个 mod 必备字段齐全（按 type 区分）
  C. aob 可解析为 hex（+ ?? 通配），长度偶数、每字节 2 字符
  D. code_inject / code_patch：hook_size 必须 >= 5（jmp rel32 占 5 字节）
  E. aob_vars：每个偏移 offset+2 <= len(aob_bytes)（防 no_recoil 8 字节错位）
  F. conflicts：引用的 id 必须存在；且必须双向声明（A 列 B ⟺ B 列 A）
  G. asm_code：{var} 占位符必须声明于 aob_vars 或 aob_refs；
     mov [mem], imm 缺尺寸前缀（byte/word/dword/qword）→ 错误（8 字节写穿崩溃类）
     add/sub/... [mem], imm 缺尺寸前缀 → 警告
  H. 共享同一 aob 的多个 mod 必须互相声明 conflicts（否则后开者 AOB not found）；
     **例外**：通过 hook_owner 复用同一 hook 的 mod（单 hook 多 flag）豁免
  I. aob_refs（多 AOB 变量引用）：每个 ref 必须有 aob（可解析）+ index（index+2<=len）；
     引用的 {name} 须在 aob_vars / aob_refs 声明
  J. 单 hook 多 flag：hook_owner 指向的 id 须存在且为 code_inject；从属 mod 须带 flag
     且该 flag 须出现在 owner 的 flags 列表；hook_owner 关系不得与 conflicts 矛盾

引擎感知：
  - generic / memory 引擎（数据驱动，AsmHelper 汇编）：跑以上全部检查。
  - 管道引擎（engine 以 _pipe 结尾，如 ra2_pipe）：AOB/asm 是引擎自有契约，
    本工具只做引擎无关的 conflicts 检查，避免误报；其余由引擎自身保证。

注意：asm 的**机器码编码**（r12 SIB、alu 尺寸等）由主仓 tools/asm-verify
用运行时完全相同的 AsmHelper 校验，发布流程见规范 §6。

用法：
  python scripts/plugin_lint.py plugins/<id> [plugins/<id> ...]
  python scripts/plugin_lint.py --all
  python scripts/plugin_lint.py --root <仓根>        # 默认脚本所在仓根

接口（供 plugins-validate.py 调用）：
  from plugin_lint import lint_memory
  errors, warnings = lint_memory(mem_dict, pid, raw_bytes=None, engine="generic")
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
GRAY = "\033[90m"
RESET = "\033[0m"

KNOWN_FLAG_VARS = {
    "health", "vehicle_health", "score", "ohk",
    "ptplayer", "ptgun", "ptenemy",
}

CODE_TYPES = ("code_inject", "code_patch")
ALU_OPS = ("mov", "add", "sub", "and", "or", "xor", "cmp")
GENERIC_ENGINES = ("generic", "memory", "")


# --------------------------------------------------------------------------
# AOB 解析
# --------------------------------------------------------------------------
def parse_aob(aob: str) -> tuple[int, bool, str]:
    """返回 (字节数, 是否合法, 错误信息)。?? 视为 1 字节通配。"""
    if not isinstance(aob, str) or not aob.strip():
        return 0, False, "aob 为空"
    clean = aob.replace("\n", " ").replace("\r", " ").split()
    n = 0
    for tok in clean:
        if tok == "??":
            n += 1
            continue
        if len(tok) != 2:
            return 0, False, f"aob 片段 {tok!r} 不是 2 字符"
        try:
            int(tok, 16)
        except ValueError:
            return 0, False, f"aob 片段 {tok!r} 不是合法 hex"
        n += 1
    if n == 0:
        return 0, False, "aob 无有效字节"
    return n, True, ""


# --------------------------------------------------------------------------
# 核心：单 mod 校验
# --------------------------------------------------------------------------
def _lint_mod(m: dict, mid: str, generic: bool, errors: list, warnings: list) -> None:
    typ = m.get("type", "value")

    # 必备字段（所有引擎）
    for fld in ("module", "aob"):
        if not m.get(fld):
            errors.append(f"{mid}: 缺必备字段 {fld!r}")

    # 管道引擎：AOB/asm 是引擎自有契约，跳过 C/D/E/G/H，只做 conflicts（F）
    if not generic:
        return

    aob = m.get("aob", "")
    nbytes, ok, msg = parse_aob(aob)
    if not ok:
        errors.append(f"{mid}: aob 非法 — {msg}")
        nbytes = 0

    if typ in CODE_TYPES:
        if typ == "code_inject":
            if not m.get("asm_code"):
                errors.append(f"{mid}: type=code_inject 缺 asm_code")
            hs = m.get("hook_size")
            if not isinstance(hs, int):
                errors.append(f"{mid}: type=code_inject 缺 hook_size")
            elif hs < 5:
                errors.append(
                    f"{mid}: hook_size={hs} < 5（jmp rel32 占 5 字节，不能 <5，否则引擎直接拒绝）")
        if typ == "code_patch" and not m.get("patch_bytes"):
            errors.append(f"{mid}: type=code_patch 缺 patch_bytes")

        # E. aob_vars 偏移越界
        av = m.get("aob_vars") or {}
        if isinstance(av, dict) and nbytes:
            for k, v in av.items():
                if not isinstance(v, int):
                    errors.append(f"{mid}.aob_vars.{k}={v!r} 不是整数字节索引")
                    continue
                if v < 0 or v + 2 > nbytes:
                    errors.append(
                        f"{mid}.aob_vars.{k}={v} 越界：AOB 仅 {nbytes} 字节，"
                        f"需满足 0 <= v 且 v+2 <= {nbytes}（变量为 2 字节）")

        # G. asm_code 检查
        if m.get("asm_code"):
            refs = m.get("aob_refs") if isinstance(m.get("aob_refs"), dict) else {}
            _lint_asm(m["asm_code"], mid, av if isinstance(av, dict) else {}, refs, errors, warnings)

        # I. aob_refs（多 AOB 变量引用）结构校验
        arefs = m.get("aob_refs")
        if arefs is not None:
            if not isinstance(arefs, dict):
                errors.append(f"{mid}: aob_refs 必须是对象")
            else:
                for rname, rdef in arefs.items():
                    if not isinstance(rdef, dict):
                        errors.append(f"{mid}.aob_refs.{rname} 必须是对象 {{aob, index}}")
                        continue
                    raob = rdef.get("aob", "")
                    rn, rok, rmsg = parse_aob(raob)
                    if not rok:
                        errors.append(f"{mid}.aob_refs.{rname}: aob 非法 — {rmsg}")
                        rn = 0
                    ridx = rdef.get("index")
                    if not isinstance(ridx, int):
                        errors.append(f"{mid}.aob_refs.{rname}.index 必须是整数字节索引")
                    elif rn and (ridx < 0 or ridx + 2 > rn):
                        errors.append(
                            f"{mid}.aob_refs.{rname}.index={ridx} 越界：AOB 仅 {rn} 字节，"
                            f"需满足 0<=index 且 index+2<={rn}（变量为 2 字节）")
    else:
        if not aob:
            errors.append(f"{mid}: type=value 缺 aob（无法定位）")
        if not m.get("value_type"):
            warnings.append(f"{mid}: type=value 建议显式写 value_type（默认 int32）")


def _lint_asm(asm: str, mid: str, aob_vars: dict, aob_refs: dict | None,
              errors: list, warnings: list) -> None:
    import re
    lines = asm.replace("\r", "").split("\n")
    var_re = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    mov_nosize = re.compile(
        r"^\s*mov\s+(?!byte\s+ptr|word\s+ptr|dword\s+ptr|qword\s+ptr)"
        r"\[\s*[^\]]*?\s*\]\s*,\s*(0x[0-9A-Fa-f]+|-?\d+)\s*$"
    )
    alu_nosize = re.compile(
        r"^\s*(add|sub|and|or|xor|cmp)\s+(?!byte\s+ptr|word\s+ptr|dword\s+ptr|qword\s+ptr)"
        r"\[\s*[^\]]*?\s*\]\s*,\s*(0x[0-9A-Fa-f]+|-?\d+)\s*$"
    )

    declared = set(aob_vars.keys()) | set((aob_refs or {}).keys())
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.endswith(":") or line.startswith(";"):
            continue
        for vname in var_re.findall(line):
            if vname not in declared:
                errors.append(
                    f"{mid}: asm 第{i}行 占位符 {{{vname}}} 未在 aob_vars 声明"
                    f"（引擎无法替换 → 「无法解析的内存操作数片段」）")
        if mov_nosize.match(line):
            errors.append(
                f"{mid}: asm 第{i}行 `mov [mem], imm` 缺尺寸前缀"
                f"（byte/word/dword/qword ptr）。默认按 32 位写，若字段本应更小会写穿相邻字节 → 崩溃。请显式写尺寸。")
        elif alu_nosize.match(line):
            warnings.append(
                f"{mid}: asm 第{i}行 `{line.split(',')[0].strip()} [mem], imm` 缺尺寸前缀，"
                f"建议显式写 byte/word/dword/qword ptr")


# --------------------------------------------------------------------------
# conflicts / 共享 AOB 校验
# --------------------------------------------------------------------------
def _lint_conflicts(mods: list, errors: list, warnings: list) -> None:
    ids = [m.get("id") for m in mods if isinstance(m, dict) and m.get("id")]
    idset = set(ids)
    conf_map: dict[str, list] = {}
    for m in mods:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        cl = m.get("conflicts") or []
        if not isinstance(cl, list):
            errors.append(f"{mid}: conflicts 必须是数组")
            continue
        conf_map[mid] = cl
        for t in cl:
            if t not in idset:
                errors.append(f"{mid}: conflicts 引用了不存在的功能 {t!r}")
    for mid, cl in conf_map.items():
        for t in cl:
            if t in conf_map and mid not in conf_map.get(t, []):
                errors.append(
                    f"{mid} 与 {t} 互斥未双向声明：{mid}.conflicts 含 {t}，"
                    f"但 {t}.conflicts 不含 {mid}。UI 置灰需双向声明，否则一方仍可被点击 → AOB 冲突")


def _lint_shared_aob(mods: list, errors: list, warnings: list) -> None:
    groups: dict[str, list] = {}
    hook_owner_of = {m.get("id"): m.get("hook_owner") for m in mods if isinstance(m, dict)}
    for m in mods:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        aob = (m.get("aob") or "").strip().upper()
        if not aob:
            continue
        groups.setdefault(aob, []).append(mid)
    for aob, members in groups.items():
        if len(members) < 2:
            continue
        conflict_of = {m.get("id"): set(m.get("conflicts") or []) for m in mods}
        bad = []
        for a in members:
            for b in members:
                if a == b:
                    continue
                if b in conflict_of.get(a, set()):
                    continue
                # 豁免：通过 hook_owner 复用同一 hook 的 mod（单 hook 多 flag，合法共存）
                ho_a, ho_b = hook_owner_of.get(a), hook_owner_of.get(b)
                if ho_a == b or ho_b == a or (ho_a and ho_a == ho_b):
                    continue
                bad.append(f"{a}↔{b}")
        if bad:
            errors.append(
                f"共用同一 AOB 的 mod {members} 未全部互相声明 conflicts"
                f"（{', '.join(sorted(set(bad)))}）；后启用者会 AOB not found / already hooked"
                f"。若本就是单 hook 多 flag，请用 hook_owner 关联而非 conflicts")


def _lint_multi_flag(mods: list, errors: list, warnings: list) -> None:
    """J. 单 hook 多 flag（flags / flag / hook_owner）一致性校验。"""
    by_id = {m.get("id"): m for m in mods if isinstance(m, dict)}
    conflict_of = {m.get("id"): set(m.get("conflicts") or []) for m in mods if isinstance(m, dict)}

    for m in mods:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        owner = m.get("hook_owner")
        flag = m.get("flag")
        flags = m.get("flags")

        # 从属 mod：必须有 hook_owner + flag
        if owner is not None:
            if owner not in by_id:
                errors.append(f"{mid}: hook_owner 指向了不存在的 mod {owner!r}")
            elif by_id[owner].get("type") != "code_inject":
                errors.append(f"{mid}: hook_owner {owner!r} 必须是 type=code_inject")
            else:
                oflags = by_id[owner].get("flags") or []
                if not isinstance(oflags, list):
                    errors.append(f"{mid}: owner {owner!r} 的 flags 必须是数组")
                elif not flag:
                    errors.append(f"{mid}: 声明了 hook_owner 但缺 flag（须指定本 mod 控制的 flag 名）")
                elif flag not in oflags:
                    errors.append(
                        f"{mid}: flag {flag!r} 不在 owner {owner!r} 的 flags 列表 {oflags} 中"
                        f"（cave 内没有对应分支，切换无效）")
            # hook_owner 关系与 conflicts 矛盾：既共享 hook 又互斥
            if owner in conflict_of.get(mid, set()) or mid in conflict_of.get(owner, set()):
                errors.append(
                    f"{mid} 与 {owner} 既声明 hook_owner 又声明 conflicts，逻辑矛盾"
                    f"：已合并为单 hook 多 flag 就不应再互斥")

        # owner 的 flags 列表应包含所有从属 mod 引用的 flag（文档完整性，仅警告）
        if flags is not None:
            if not isinstance(flags, list):
                errors.append(f"{mid}: flags 必须是数组")
            elif owner is not None:
                warnings.append(f"{mid}: 同时带 flags 与 hook_owner，flags 仅 owner 使用，从属 mod 忽略")


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def lint_memory(mem: dict, pid: str, raw_bytes: bytes | None = None,
                engine: str = "generic") -> tuple[list, list]:
    """返回 (errors, warnings)。可被 plugins-validate.py 调用。"""
    errors: list = []
    warnings: list = []
    if raw_bytes is not None and raw_bytes[:3] == b"\xef\xbb\xbf":
        errors.append("memory.json 含 UTF-8 BOM，严格 JSON 解析器会失败，必须去除")
    if not isinstance(mem, dict):
        errors.append("memory.json 顶层不是对象")
        return errors, warnings
    mods = mem.get("mods")
    if not isinstance(mods, list) or not mods:
        errors.append("缺少 mods 数组或为空")
        return errors, warnings

    generic = engine in GENERIC_ENGINES
    if not generic:
        warnings.append(
            f"引擎 {engine!r} 为管道引擎，跳过 AOB/asm 语义检查（由引擎自身保证）；"
            f"仅校验 conflicts 双向一致性")

    seen: set = set()
    for m in mods:
        if not isinstance(m, dict):
            errors.append("mod 不是对象")
            continue
        mid = m.get("id")
        if not mid:
            errors.append("mod 缺 id")
            continue
        if mid in seen:
            errors.append(f"mod id 重复: {mid}")
        seen.add(mid)
        _lint_mod(m, mid, generic, errors, warnings)

    _lint_conflicts(mods, errors, warnings)
    if generic:
        _lint_shared_aob(mods, errors, warnings)
        _lint_multi_flag(mods, errors, warnings)
    return errors, warnings


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _lint_path(p: Path) -> tuple[list, list]:
    raw = p.read_bytes()
    try:
        mem = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e.msg} (第 {e.lineno} 行)"], []
    pid = p.parent.name
    engine = "generic"
    mf_path = p.parent / "manifest.json"
    if mf_path.exists():
        try:
            mf = json.loads(mf_path.read_text(encoding="utf-8-sig"))
            engine = mf.get("engine", "generic") or "generic"
        except Exception:
            pass
    return lint_memory(mem, pid, raw, engine)


def main() -> int:
    ap = argparse.ArgumentParser(description="插件 memory.json 语义校验")
    ap.add_argument("paths", nargs="*", help="plugins/<id> 目录或 memory.json 路径")
    ap.add_argument("--all", action="store_true", help="校验仓内所有插件")
    ap.add_argument("--root", default=None, help="仓根（默认脚本所在目录的父级）")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    targets: list[Path] = []
    if args.all:
        targets = sorted((root / "plugins").glob("*/memory.json"))
    elif args.paths:
        for p in args.paths:
            pp = Path(p)
            if pp.is_dir():
                targets.append(pp / "memory.json")
            else:
                targets.append(pp)
    else:
        print("用法: python scripts/plugin_lint.py plugins/<id> | --all", file=sys.stderr)
        return 2

    if not targets:
        print(f"{RED}未找到任何 memory.json{RESET}", file=sys.stderr)
        return 2

    total_err = 0
    for mem_path in targets:
        if not mem_path.exists():
            print(f"{RED}[缺失] {mem_path}{RESET}")
            total_err += 1
            continue
        pid = mem_path.parent.name
        errs, warns = _lint_path(mem_path)
        total_err += len(errs)
        head = f"{GREEN}✅ {pid}{RESET}" if not errs else f"{RED}❌ {pid}{RESET}"
        print(f"\n{head}  ({mem_path})")
        for e in errs:
            print(f"  {RED}ERROR{RESET}  {e}")
        for w in warns:
            print(f"  {YELLOW}WARN{RESET}   {w}")
        if not errs and not warns:
            print(f"  {GRAY}无问题{RESET}")

    print(f"\n===== plugin_lint: 错误 {total_err} =====")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
