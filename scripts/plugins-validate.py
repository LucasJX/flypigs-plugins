#!/usr/bin/env python3
"""plugins-validate.py — flypigs-plugins 仓校验脚本（Plugin Spec v1.0）

校验项：
  1. index.json (schema v2) 合法 + market_base 字段齐
  2. plugins/<id>/ 目录 与 index.json.plugins[] 条目一一对应
  3. zip 包：sha256 == index.json.plugins[i].sha256, size == size,
     文件名 <id>-<version>.zip 与 manifest.id/version 一致
  4. manifest.json 合法，字段齐全；features_count == features.length
  5. **groups 铁律**：有序数组、去重；每条 feature 都命中（未命中归"其他" + 报警告）
  6. fn_kind ∈ {button, checkbox, slider, input, select, multi_select, protected_list}
  7. 除 button/protected_list 外，fn_label 必填（protected_list 走整个阵营列表协议，不是单 label）
  8. memory.json / game.json（可选）合法
  9. zip 内 manifest.json 与仓根 manifest.json 内容字节相同
 10. zip 内无越界路径（zip-slip 防护）
 11. zip 内 main 文件 (manifest / memory / game) 没有残留 .bak/_v2 等

用法：
  python scripts/plugins-validate.py                     # 校验所有 plugins/
  python scripts/plugins-validate.py plugins/<id> ...    # 校验指定插件
  python scripts/plugins-validate.py --strict           # 警告也升级为错误
  python scripts/plugins-validate.py --root .           # 显式指仓根（默认自动）

退出码：0 = 全过；1 = 错误；2 = 仅警告（--strict 下变 1）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

# AUD-026-B：规则单一真源。两 validator 共用 schema.py，禁止各自维护规则副本。
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import schema

# --- 常量 ---

# AUD-026-B：fn_kind 集合与 fn_label 豁免规则由 schema.py 提供（单一真源）。
VALID_FN_KIND = schema.VALID_FN_KIND
LABEL_OPT_OUT_KIND = schema.LABEL_OPT_OUT_KIND
PATH_SAFE = re.compile(r"^([A-Za-z0-9_./-]+)$")

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
GRAY = "\033[90m"
RESET = "\033[0m"

# 简易 io：3.13 之前 print 还支持 flush 参数；>=3.3 默认 flush-on-newline 仍可关。
def _stdout() -> "Any":
    return sys.stdout

# --- 校验器 ---

class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []   # 红色，必须修
        self.warnings: list[str] = [] # 黄色，建议改
        self.passed: list[str] = []   # 灰色，简洁清单

    def add_error(self, where: str, msg: str) -> None:
        self.errors.append(f"[{where}] {msg}")

    def add_warning(self, where: str, msg: str) -> None:
        self.warnings.append(f"[{where}] {msg}")

    def add_pass(self, what: str) -> None:
        self.passed.append(what)

    def is_clean(self) -> bool:
        return not self.errors


# --- 基线（既存 warning 白名单）------------------------------------------------
# 为什么要基线：--strict 一旦被既存 warning 永久钉死，就没人愿意拿它当 CI 闸门，
# 于是「新增一条问题」和「一直存在的老问题」混在一起无法区分。
# 基线制把「已登记、已评估、可接受」的既存 warning 显式记下来，
# strict 只对**基线之外的新增 warning** 失败——既不掩盖老问题，也不让闸门永远红。
#
# 基线文件格式：每行一条 warning 签名（按**子串**匹配 warning 全文），'#' 开头为注释。
# 新增 warning 应当在 strict 失败后，把签名登记进基线并写明「为什么可接受」。

def _load_baseline(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _split_baseline(warnings: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """把 warning 分成 (基线内, 新增)。按子串匹配。"""
    if not baseline:
        return [], list(warnings)
    known: list[str] = []
    fresh: list[str] = []
    for w in warnings:
        if any(sig in w for sig in baseline):
            known.append(w)
        else:
            fresh.append(w)
    return known, fresh


def _read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e.msg} ({path.name} 第 {e.lineno} 行第 {e.colno} 列)"
    except OSError as e:
        return None, f"读取失败: {e}"


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_safe_zip_member(name: str, where: str, res: Result) -> None:
    """防止 zip-slip：拒绝 .. 段、超长或非 ASCII 路径"""
    if ".." in name.replace("\\", "/").split("/"):
        res.add_error(where, f"zip 内路径含 '..' 段，禁止: {name!r}")
    elif not PATH_SAFE.match(name):
        # 允许中英混排（去掉 ASCII-only 限制）；单独检查控制字符
        if any(ord(c) < 0x20 for c in name):
            res.add_error(where, f"zip 内路径含控制字符，禁止: {name!r}")


def _parse_hex_bytes_check(hex_str: str) -> bool:
    """校验 hex 字符串合法（允许空格分隔）。与 MemoryEngine.ParseHexBytes 行为一致。"""
    if not hex_str: return False
    clean = hex_str.replace(" ", "").replace("\t", "").replace("\n", "").replace("\r", "")
    if not clean or len(clean) % 2 != 0:
        return False
    try:
        bytes.fromhex(clean)
        return True
    except ValueError:
        return False


def _check_plugin(plugin_dir: Path, index_entries: dict, res: Result) -> None:
    """校验单个 plugins/<id>/ 目录（含 index.json 对齐项）"""
    pid = plugin_dir.name
    where = f"plugins/{pid}"

    # --- manifest.json ---
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        res.add_error(where, "缺 manifest.json（必备）")
        return  # 没 manifest 后面都没法校
    mf, err = _read_json(manifest_path)
    if err:
        res.add_error(where, err)
        return
    res.add_pass(f"manifest.json 合法 ({manifest_path.stat().st_size}B)")

    # manifest schema
    required_top = ["id", "name", "process", "engine", "version", "features"]
    for k in required_top:
        if k not in mf:
            res.add_error(where, f"manifest 缺字段: {k!r}")

    if mf.get("id") != pid:
        res.add_error(where, f"manifest.id={mf.get('id')!r} 与目录名 {pid!r} 不一致")
    if not isinstance(mf.get("features"), list):
        res.add_error(where, "manifest.features 必须是数组")
    if not isinstance(mf.get("version"), str) or not re.match(r"^\d+\.\d+\.\d+", mf["version"]):
        res.add_error(where, f"manifest.version 必须是 semver: {mf.get('version')!r}")

    # groups（铁律）
    groups = mf.get("groups")
    if not isinstance(groups, list) or len(groups) == 0:
        res.add_error(where, "manifest.groups 必须是有序数组且 ≥ 1 项（铁律）")
    else:
        if list(dict.fromkeys(groups)) != groups:
            res.add_error(where, f"manifest.groups 含重复: {groups}")
        for g in groups:
            if g == "其他":
                res.add_warning(where, "manifest.groups 含 '其他' — 这是兜底组，不应在产品插件声明")
        res.add_pass(f"groups 有序数组 {len(groups)} 项: {groups}")

    # features 内联校验
    seen_ids = set()
    ungrouped: list[str] = []
    if isinstance(mf.get("features"), list) and isinstance(groups, list):
        for ft in mf["features"]:
            if not isinstance(ft, dict):
                res.add_error(where, f"feature 不是对象: {ft!r}")
                continue
            fid = ft.get("id")
            if not isinstance(fid, str) or not fid:
                res.add_error(where, f"feature 缺 id: {ft!r}")
                continue
            if fid in seen_ids:
                res.add_error(where, f"feature id 重复: {fid!r}")
            seen_ids.add(fid)
            fkind = ft.get("fn_kind") or ft.get("type")
            if fkind not in VALID_FN_KIND:
                res.add_warning(where, f"feature {fid!r} fn_kind={fkind!r} 不在 {sorted(VALID_FN_KIND)}")
            # fn_label 只在 legacy_label 能力类（ra2_pipe / legacy_label）必需（AUD-026-B）。
            # 判定用 schema 能力类而非 engine 字符串后缀：旧 endswith('_pipe') 会把
            # data_driven 的 injected_pipe 误判为注入式（JC3 曾被误报 12 个假错误）。
            engine = mf.get("engine", "") or ""
            if schema.fn_label_required(fkind, engine) and not ft.get("fn_label"):
                res.add_error(where, f"feature {fid!r} (kind={fkind}, engine={engine}) 缺 fn_label — legacy_label 引擎必需")
            # group 命中检查留给 memory.mods（manifest.features 是 UI 描述，不要求 group）

    # --- memory.json（可选） ---
    mem_path = plugin_dir / "memory.json"
    mem = None
    if mem_path.exists():
        mem, err = _read_json(mem_path)
        if err:
            res.add_error(where, err)
        else:
            res.add_pass(f"memory.json 合法 ({mem_path.stat().st_size}B)")
            # --- memory.json 语义校验（Plugin Spec v2.0）---
            # 调用同目录的 plugin-lint.py（失败也不影响本脚本其余检查）。
            try:
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location(
                    "plugin_lint", str(Path(__file__).resolve().parent / "plugin_lint.py"))
                if _spec and _spec.loader:
                    _pl = _ilu.module_from_spec(_spec)
                    _spec.loader.exec_module(_pl)
                    _me, _mw = _pl.lint_memory(
                        mem, pid, mem_path.read_bytes(),
                        engine=(mf.get("engine") or "generic"))
                    for _e in _me:
                        res.add_error(where + "/memory", _e)
                    for _w in _mw:
                        res.add_warning(where + "/memory", _w)
            except Exception as _ex:  # 语义检查本身异常不应阻断结构校验
                res.add_warning(where + "/memory", f"plugin_lint 调用失败（跳过语义检查）: {_ex}")

    # features_count 一致性（manifest 必填，对齐主功能集合数 = features.length - 备用 _2/_alt/_备用）
    features_list = mf.get("features") if isinstance(mf.get("features"), list) else []
    mods_list = mem.get("mods") if mem and isinstance(mem.get("mods"), list) else []
    features_count = mf.get("features_count")
    if features_count is None:
        res.add_error(where, "manifest.features_count 必填（Plugin Spec v1.0）")
    else:
        # 主 mod 集合：去掉 _2/_alt/_备用 后缀的备用 mod
        main_features_count = schema.expected_features_count(features_list)
        if isinstance(features_count, int) and features_count != main_features_count:
            res.add_error(where,
                f"manifest.features_count={features_count} 应等于主功能数 {main_features_count}（去除备用 _2/_alt/_备用）")

    # 1:1 对齐（Plugin Spec v1.0 铁律）：manifest.features[].id 与 memory.mods[].id 必须一一对应
    # （备用 mod 用 suffix _alt / _2 / _备用 会被识别为非主 mod，跳过对齐要求）
    if features_list and mods_list:
        main_features = [f.get("id") for f in features_list if isinstance(f, dict) and f.get("id")
                         and not schema.is_alt_id(f.get("id", ""))]
        main_mods = [m.get("id") for m in mods_list if isinstance(m, dict) and m.get("id")
                     and not schema.is_alt_id(m.get("id", ""))]
        only_in_features = set(main_features) - set(main_mods)
        only_in_mods = set(main_mods) - set(main_features)
        if only_in_features:
            res.add_warning(where,
                f"manifest 有但 memory 无（声明了 UI 但没实现）: {sorted(only_in_features)}")
        if only_in_mods:
            res.add_warning(where,
                f"memory 有但 manifest 无（实现了但没暴露给 UI）: {sorted(only_in_mods)}")

    # legacy_label（RA2）插件：fn_kind 是「引擎协议类型」（决定下发 button/checkbox/
    # slider/input 哪种事件），memory.mods 是真源，manifest.features 必须与之一致。
    # 不一致时，客户端详情页（按 manifest 的 type 渲染）会给出与引擎不匹配的控件：
    # 2026-10-21 实测 RA2「钱」在 manifest 里被写成 button，而引擎 kApply 走 input 事件
    # → 详情页只剩「触发」按钮、金额写死，且与「游戏」控制页行为不一致。
    # 同时 type（UI 控件类型）必须与 fn_kind 同值：legacy_label 插件的 memory.mods
    # 没有独立的 mod type（data_driven 才有 code_inject/code_patch），两者本就该同值。
    if features_list and mods_list and schema.resolve_engine_class(mf.get("engine")) == "legacy_label":
        by_f = {f.get("id"): f for f in features_list if isinstance(f, dict)}
        for m in mods_list:
            if not isinstance(m, dict):
                continue
            mid = m.get("id") or "?"
            f = by_f.get(m.get("id"))
            if not f:
                continue
            mk, fk = m.get("fn_kind"), f.get("fn_kind")
            if mk and fk and mk != fk:
                res.add_error(where,
                              f"mod {mid!r} fn_kind 不一致: memory={mk!r} vs manifest={fk!r}"
                              "（legacy_label 的 fn_kind 是引擎协议类型，两处必须一致）")
            ft = f.get("type")
            if ft and mk and ft != mk:
                res.add_error(where,
                              f"mod {mid!r} 的 features[].type={ft!r} 与 fn_kind={mk!r} 不一致"
                              "（type 是 UI 控件类型，legacy_label 下必须与 fn_kind 同值）")

    # --- 事件类型铁律（2026-10-21 新增，error 级）-----------------------------
    # 「触发功能却变成了开关/输入框」这类错位的根因：插件数据把 fn_kind 写错，
    # 而客户端既按 fn_kind 渲染控件、也按 fn_kind 派发引擎事件 —— 写错就两头对不上。
    # 权威来源 = 引擎的 On*Event 分派（ra2_yr trainer.cc），已固化进 schema.py。
    # ⚠️ 不能以 model.h 的 enum 注释为准：那里把 kApply 标在 "// Button" 段，
    #    但引擎实际走 OnInputEvent（写金钱）——照注释改就是本次修掉的原 bug。
    engine_class = schema.resolve_engine_class(mf.get("engine"))
    if engine_class == "legacy_label" and mods_list and features_list:
        by_id = {m.get("id"): m for m in mods_list if isinstance(m, dict)}
        for f in features_list:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            m = by_id.get(fid)
            if not m:
                continue
            label = m.get("fn_label") or f.get("fn_label") or ""
            expected = schema.fn_label_event_kind(label)
            if not expected:
                continue
            for field in ("fn_kind", "type"):
                got = f.get(field)
                if got and got != expected:
                    res.add_error(where,
                                  f"feature {fid!r} 的 {field}={got!r} 与引擎事件类型不符"
                                  f"（fn_label={label!r} 实际是 {expected!r}）"
                                  " —— 声明成别的控件会与引擎派发对不上"
                                  "（权威表：scripts/schema.py::FN_LABEL_EVENT_KIND）")
            mk = m.get("fn_kind")
            if mk and mk != expected:
                res.add_error(where,
                              f"mod {fid!r} 的 fn_kind={mk!r} 与引擎事件类型不符"
                              f"（fn_label={label!r} 实际是 {expected!r}）"
                              "（权威表：scripts/schema.py::FN_LABEL_EVENT_KIND）")

    # --- 可逆 mod 必须是开关（2026-10-21 新增，error 级）---------------------
    # code_patch / code_inject 在禁用时能真正还原（还原原字节 / 释放 cave），
    # 声明成一次性「触发」按钮 = 用户开了就再也关不掉。
    # 2026-10-21 实测：JC3 的 easy_clear_heat / unlock_all_gear_mods /
    # add_10k_challenge_score 三项都是 code_inject，却被声明成 button。
    if engine_class == "data_driven" and mods_list and features_list:
        by_id = {m.get("id"): m for m in mods_list if isinstance(m, dict)}
        for f in features_list:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            m = by_id.get(fid)
            if not m:
                continue
            if not schema.is_reversible_mod(m.get("type")):
                continue
            for field in ("fn_kind", "type"):
                if f.get(field) == "button":
                    res.add_error(where,
                                  f"feature {fid!r} 的 {field}='button' 不可接受"
                                  f"（mod.type={m.get('type')!r} 是可逆的，禁用能还原）"
                                  " —— 可逆 mod 必须声明成 checkbox 开关，"
                                  "声明成 button 会让用户开了关不掉")

    # --- 权威中文名（2026-10-21 新增，error 级）-----------------------------
    # RA2 插件是原 trainer 的移植，功能名必须与引擎里的权威文案一致
    # （char_table.h 的 GetFnStrZh / GetGuiStrZh），否则同一功能在
    # 「插件详情页」（读 manifest.features[].name）与「游戏控制页」（读 memory.mods[].name）
    # 会叫成两个名字 —— 2026-10-21 用户报的「中文对应翻译有问题」就是这条。
    if engine_class == "legacy_label" and mods_list:
        by_id = {m.get("id"): m for m in mods_list if isinstance(m, dict)}
        for m in mods_list:
            if not isinstance(m, dict):
                continue
            mid = m.get("id") or "?"
            expected_zh = schema.authoritative_zh_name(m.get("fn_label"), mid)
            if not expected_zh:
                continue
            got = m.get("name")
            if got != expected_zh:
                res.add_error(where,
                              f"mod {mid!r} 的中文名 {got!r} 与引擎权威文案 {expected_zh!r} 不一致"
                              "（权威表：char_table.h GetFnStrZh/GetGuiStrZh，"
                              "见 scripts/schema.py::FN_LABEL_ZH_NAMES）")
        for f in features_list:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            m = by_id.get(fid)
            if not m:
                continue
            expected_zh = schema.authoritative_zh_name(m.get("fn_label"), fid)
            if not expected_zh:
                continue
            got = f.get("name")
            if got and got != expected_zh:
                res.add_error(where,
                              f"feature {fid!r} 的中文名 {got!r} 与引擎权威文案 {expected_zh!r} 不一致"
                              "（详情页读 manifest 的 name，控制页读 memory 的 name，"
                              "两处不一致就会出现「同名不同叫」）")

    # --- 权威分组（2026-10-21 新增，error 级）-------------------------------
    # 分组也是引擎的权威数据（main.js CATEGORY_OF + index.html 分组标题）。
    # 2026-10-21 实测：AdjustGameSpeed 被单独放进「任务调速」组，而原 trainer 里
    # 它是战场控制组底部的独立滑杆块 —— 凭空多出一个分组，用户看到的结构就与原版不一致。
    if engine_class == "legacy_label" and mods_list:
        for m in mods_list:
            if not isinstance(m, dict):
                continue
            mid = m.get("id") or "?"
            expected_group = schema.authoritative_group(m.get("fn_label"), mid)
            if not expected_group:
                continue
            got = m.get("group")
            if got != expected_group:
                res.add_error(where,
                              f"mod {mid!r} 的分组 {got!r} 与引擎权威分组 {expected_group!r} 不一致"
                              "（权威表：main.js CATEGORY_OF + index.html 分组标题，"
                              "见 scripts/schema.py::FN_LABEL_GROUP）")

    # 归组铁律：memory.mods[].group 必须命中 manifest.groups（**这条才是真正的"分组铁律"**）
    if mods_list and isinstance(groups, list):
        ungrouped: list[str] = []
        for m in mods_list:
            if not isinstance(m, dict):
                continue
            mg = m.get("group")
            mid = m.get("id") or "?"
            if mg not in groups:
                ungrouped.append(f"{mid}→{mg}")
        if ungrouped:
            res.add_error(where,
                f"{len(ungrouped)} 条 memory.mods 未命中 manifest.groups（归组铁律！客户端会归 '其他' 兜底组）："
                + ", ".join(ungrouped[:5]) + ("..." if len(ungrouped) > 5 else ""))

    # v2.7 AutoAssembler：memory.mods[].type 分发 + 字段必填校验
    if mods_list:
        for m in mods_list:
            if not isinstance(m, dict): continue
            mid = m.get("id", "?")
            mt = (m.get("type", "value") or "value").lower()
            if mt not in ("value", "code_patch", "code_inject"):
                res.add_error(where, f"mod {mid!r} type={m.get('type')!r} 必须 ∈ value/code_patch/code_inject")
                continue
            if mt == "code_patch":
                if not m.get("patch_bytes"):
                    res.add_error(where, f"mod {mid!r} type=code_patch 缺 patch_bytes（hex 字符串）")
                elif _parse_hex_bytes_check(m["patch_bytes"]) is not True:
                    res.add_error(where, f"mod {mid!r} patch_bytes 不是合法 hex")
                # patch_offset 缺省 0
                off = m.get("patch_offset", 0)
                if not isinstance(off, int) or off < 0:
                    res.add_error(where, f"mod {mid!r} patch_offset 必须是 ≥0 整数")
            elif mt == "code_inject":
                if not m.get("asm_code"):
                    res.add_error(where, f"mod {mid!r} type=code_inject 缺 asm_code")
                else:
                    if _parse_hex_bytes_check(m["asm_code"]) is not True:
                        # asm 文本格式（多行 / 含 mnemonics），MemoryEngine.AsmHelper 会用自实现汇编器编码
                        # 加 warning 而非 error：asm 文本经 AsmHelper 编译后仍是合法机器码，
                        # 但 AsmHelper 只支持有限指令集（mov/add/sub/jmp/call 等），
                        # 写出来的 SIMD/复杂指令会在游戏内运行时报 NotSupportedException
                        res.add_warning(where,
                            f"mod {mid!r} asm_code 是 asm 文本格式（不是 hex）——"
                            f"需 MemoryEngine.AsmHelper 支持，未测指令可能运行时报错。"
                            f"Plugin Spec v1.0 建议优先 hex 字节，文本仅作过渡")
                hs = m.get("hook_size", 5)
                if not isinstance(hs, int) or hs < 5 or hs > 32:
                    res.add_error(where, f"mod {mid!r} hook_size={hs} 必须在 [5..32]")
                # code_inject 必须有 aob（命中点就是 hook 位置）
                if not m.get("aob"):
                    res.add_error(where, f"mod {mid!r} type=code_inject 缺 aob（命中点 = hook 位置）")
        res.add_pass(f"AutoAssembler type 校验：{len(mods_list)} 条 mod 检查完")

    # --- game.json（可选） ---
    game_path = plugin_dir / "game.json"
    game = None
    if game_path.exists():
        game, err = _read_json(game_path)
        if err:
            res.add_error(where, err)
        else:
            res.add_pass(f"game.json 合法 ({game_path.stat().st_size}B)")
            if game.get("id") != pid:
                res.add_error(where, f"game.json.id={game.get('id')!r} 与目录名 {pid!r} 不一致")
            if not game.get("name"):
                res.add_error(where, "game.json.name 必填")
            proc_raw = game.get("process")
            if proc_raw is None:
                res.add_warning(where, "game.json.process 缺失 — UI 会回退到 manifest.process")
            elif not (isinstance(proc_raw, str) or (isinstance(proc_raw, list) and all(isinstance(x, str) for x in proc_raw))):
                res.add_error(where, "game.json.process 必须是 string 或 string 数组")

            # v2.8: sgdb_game_id 是强烈建议字段（v2.8+），缺了 warning 提醒（不阻塞 PR）
            sgdb_id = game.get("sgdb_game_id")
            if not isinstance(sgdb_id, int) or sgdb_id <= 0:
                res.add_warning(where,
                    "game.json.sgdb_game_id 缺失或非正整数 — PC 端不会自动拉真海报，"
                    "会回退到双色占位 PNG。建议填 SteamGridDB game_id（v2.8+ SOP）")

    # --- zip 包 ---
    index_entry = index_entries.get(pid)
    if index_entry is None:
        res.add_error(where, "index.json 没有该插件的条目（漏登）")
        return

    version_in_manifest = mf.get("version", "")
    expected_zip_name = f"{pid}-{version_in_manifest}.zip"
    zip_path = plugin_dir / expected_zip_name
    if not zip_path.exists():
        res.add_error(where, f"缺 zip 文件: {expected_zip_name}")
        return

    size = zip_path.stat().st_size
    sha = _sha256_hex(zip_path)

    if sha != index_entry.get("sha256", "").lower():
        res.add_error(where, f"sha256 不一致: zip 实际 {sha[:16]}… vs index {index_entry.get('sha256','')[:16]}…")
    else:
        res.add_pass(f"sha256 一致 ({sha[:12]}…)")

    if size != index_entry.get("size"):
        res.add_error(where, f"size 不一致: zip 实际 {size} vs index {index_entry.get('size')}")
    else:
        res.add_pass(f"size 一致 ({size}B)")

    # index.json.features_count 必须与 manifest.features_count 一致。
    # 市场卡片显示的是 index.features_count（桌面 MarketPanel/DashboardPanel +
    # 手机 market_plugin.dart 都读它），插件详情页显示的是 manifest.features.Count，
    # 两处不同源且此前**没有任何校验** → 卡片写「31 项功能」而详情页写 32 项（2026-10-21 实测）。
    # 这条是口径统一（AUD-040）的落地闸门。
    idx_fc = index_entry.get("features_count")
    mf_fc = mf.get("features_count")
    if not isinstance(idx_fc, int):
        res.add_error(where, "index.json.features_count 必填且必须为整数（市场卡片直接显示该数字）")
    elif isinstance(mf_fc, int) and idx_fc != mf_fc:
        res.add_error(where,
                      f"index.json.features_count={idx_fc} != manifest.features_count={mf_fc}"
                      "（市场卡片与详情页显示的功能数会打架）")
    else:
        res.add_pass(f"index.json.features_count 一致 ({idx_fc})")

    download = index_entry.get("download", "")
    if download and not download.endswith(expected_zip_name):
        res.add_warning(where, f"index.json.download 文件名 {download.split('/')[-1]!r} ≠ {expected_zip_name!r}")

    # --- zip 内部 ---
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # 路径安全
            for n in names:
                _check_safe_zip_member(n, where, res)
            # 必须有 manifest.json
            if "manifest.json" not in names:
                res.add_error(where, "zip 内缺 manifest.json")
            else:
                zip_manifest = zf.read("manifest.json")
                with manifest_path.open("rb") as f:
                    disk_manifest = f.read()
                if zip_manifest.replace(b"\r\n", b"\n") != disk_manifest.replace(b"\r\n", b"\n"):
                    res.add_error(where, "zip 内 manifest.json 与仓根 manifest.json 字节不一致")
                else:
                    res.add_pass("zip 内 manifest.json == 仓根 manifest.json")
            # 残留检测：不应有 .bak / _v2 等
            for n in names:
                bn = Path(n).name
                if any(suf in bn for suf in (".bak", "_v2.", "_old.", ".tmp", ".swp", "~$")):
                    res.add_warning(where, f"zip 内残留中间文件: {n}")
    except zipfile.BadZipFile as e:
        res.add_error(where, f"zip 损坏: {e}")


def _check_index_json(root: Path, res: Result) -> dict[str, dict]:
    """校验 index.json 并返回 {plugin_id: entry} 映射"""
    index_path = root / "index.json"
    if not index_path.exists():
        res.add_error("index.json", "缺仓根 index.json")
        return {}
    idx, err = _read_json(index_path)
    if err:
        res.add_error("index.json", err)
        return {}

    if idx.get("schema_version") != 2:
        res.add_error("index.json", f"schema_version 必须 = 2，当前 {idx.get('schema_version')!r}")
    if not idx.get("market_base"):
        res.add_error("index.json", "缺 market_base")
    if not idx.get("updated_at"):
        res.add_warning("index.json", "updated_at 缺失 — 客户端拿不到「市场更新于…」时间")
    plugins_arr = idx.get("plugins")
    if not isinstance(plugins_arr, list):
        res.add_error("index.json", "plugins 必须是数组")
        return {}

    entries: dict[str, dict] = {}
    for i, e in enumerate(plugins_arr):
        loc = f"index.json.plugins[{i}]"
        if not isinstance(e, dict):
            res.add_error(loc, "不是对象")
            continue
        for k in ("id", "name", "download", "sha256", "groups"):
            if k not in e:
                res.add_error(loc, f"缺字段 {k!r}")
        eid = e.get("id")
        if eid in entries:
            res.add_error(loc, f"id 重复: {eid!r}")
        entries[eid] = e
        # groups 有序校验
        gs = e.get("groups")
        if isinstance(gs, list) and list(dict.fromkeys(gs)) != gs:
            res.add_error(loc, f"groups 含重复: {gs}")

    res.add_pass(f"index.json 合法：{len(entries)} 个条目")
    return entries


def _check_plugins_root_and_index(root: Path, entries: dict[str, dict], res: Result) -> None:
    """plugins/ 目录每个子目录都应在 index.json；index.json 也不应引不存在的目录"""
    plugins_dir = root / "plugins"
    if not plugins_dir.exists():
        res.add_error("plugins/", "plugins/ 目录不存在")
        return
    disk_ids = {p.name for p in plugins_dir.iterdir() if p.is_dir()}
    index_ids = set(entries.keys())

    orphan_dirs = disk_ids - index_ids
    for pid in orphan_dirs:
        res.add_warning("plugins/", f"plugins/{pid}/ 存在但 index.json 没登 — 客户端拿不到")
    missing_dirs = index_ids - disk_ids
    for pid in missing_dirs:
        res.add_error("plugins/", f"index.json 登了 plugins/{pid} 但仓里没目录")


# --- 主入口 ---

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="要校验的 plugins/<id> 路径（缺省扫全部）")
    ap.add_argument("--root", default=".", help="仓根路径，默认当前目录")
    ap.add_argument("--strict", action="store_true", help="警告升级为错误（基线内的既存 warning 不算）")
    ap.add_argument("--baseline", default="", help="既存 warning 基线文件（默认 scripts/validate_baseline.txt，存在即生效）")
    ap.add_argument("--quiet", action="store_true", help="只打印问题，隐藏 passed 清单")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "index.json").exists():
        print(f"{RED}未找到 {root / 'index.json'}，请指定仓根（--root）{RESET}", file=sys.stderr)
        return 1
    # 基线文件默认取仓内 scripts/validate_baseline.txt（存在即生效）
    if not args.baseline:
        _default_bl = root / "scripts" / "validate_baseline.txt"
        if _default_bl.exists():
            args.baseline = str(_default_bl)

    overall = Result()
    entries = _check_index_json(root, overall)
    if not entries:
        # index.json 已经死了，没法继续
        return _report(overall, args)

    if args.targets:
        targets = []
        for t in args.targets:
            p = (Path(t) if Path(t).is_absolute() else root / t).resolve()
            if not p.exists():
                overall.add_error("CLI", f"指定路径不存在: {t}")
                continue
            targets.append(p)
    else:
        targets = sorted((root / "plugins").iterdir()) if (root / "plugins").exists() else []

    # 单一目录校验
    if targets:
        for t in targets:
            pid = t.name
            _check_plugin(t, entries, overall)
    else:
        # 全扫：让目录和 index.json 对齐（避免漏掉）
        _check_plugins_root_and_index(root, entries, overall)

    # 双向一致性（即使有 --targets 也要补一份全集对齐）
    if targets:
        _check_plugins_root_and_index(root, entries, overall)

    return _report(overall, args)


def _report(res: Result, args: Any) -> int:
    baseline = _load_baseline(Path(args.baseline)) if args.baseline else []
    known, fresh = _split_baseline(res.warnings, baseline)

    if not args.quiet:
        for p in res.passed:
            print(f"{GRAY}✓{RESET} {p}")
    for w in known:
        print(f"{GRAY}BASE{RESET} {w}")
    for w in fresh:
        print(f"{YELLOW}WARN{RESET} {w}")
    for e in res.errors:
        print(f"{RED}ERROR{RESET} {e}")

    if res.errors:
        print(f"\n{RED}FAILED{RESET} — {len(res.errors)} errors, {len(fresh)} warnings (+{len(known)} baseline)")
        return 1
    if fresh and args.strict:
        print(f"\n{YELLOW}FAILED (strict){RESET} — {len(fresh)} new warning(s)（另有 {len(known)} 条在基线内，已接受）")
        print("  新增 warning 会让闸门变红：要么修掉，要么评估后登记进基线文件并写明理由。")
        return 1
    if fresh:
        print(f"\n{YELLOW}PASSED{RESET} with {len(fresh)} warning(s)（另有 {len(known)} 条在基线内，已接受）")
        return 0
    print(f"\n{GREEN}PASSED{RESET}（{len(known)} 条 warning 在基线内，已接受）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
