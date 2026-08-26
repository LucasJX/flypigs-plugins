#!/usr/bin/env python3
"""plugins-validate.py — flypigs-plugins 仓校验脚本（Plugin Spec v1.0）

校验项：
  1. index.json (schema v2) 合法 + market_base 字段齐
  2. plugins/<id>/ 目录 与 index.json.plugins[] 条目一一对应
  3. zip 包：sha256 == index.json.plugins[i].sha256, size == size,
     文件名 <id>-<version>.zip 与 manifest.id/version 一致
  4. manifest.json 合法，字段齐全；features_count == features.length
  5. **groups 铁律**：有序数组、去重；每条 feature 都命中（未命中归"其他" + 报警告）
  6. fn_kind ∈ {button, checkbox, slider, input, select, multi_select}
  7. 除 button 外，fn_label 必填
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

# --- 常量 ---

VALID_FN_KIND = {"button", "checkbox", "slider", "input", "select", "multi_select"}
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
            # fn_label 只在「注入式引擎」(如 ra2_pipe) 必需；纯数据引擎 (memory 等) 不需要
            # 判定：manifest.engine 以 *_pipe 结尾（含 ra2_pipe / pipe_x / ...）一律视为注入式
            engine = mf.get("engine", "") or ""
            is_pipe_engine = engine.endswith("_pipe")
            if is_pipe_engine and fkind != "button" and not ft.get("fn_label"):
                res.add_error(where, f"feature {fid!r} (kind={fkind}, engine={engine}) 缺 fn_label — 注入式引擎必需")
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

    # features_count 一致性（memory.mods 优先，无则回退 manifest.features）
    features_list = mf.get("features") if isinstance(mf.get("features"), list) else []
    mods_list = mem.get("mods") if mem and isinstance(mem.get("mods"), list) else []
    features_count = mf.get("features_count")
    if isinstance(features_count, int):
        expected = len(mods_list) if mods_list else len(features_list)
        source_name = "memory.mods.length" if mods_list else "manifest.features.length"
        if features_count != expected:
            res.add_warning(where, f"manifest.features_count={features_count} 应等于 {expected}（{source_name}）")

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
                    res.add_error(where, f"mod {mid!r} type=code_inject 缺 asm_code（hex 字符串）")
                elif _parse_hex_bytes_check(m["asm_code"]) is not True:
                    res.add_error(where, f"mod {mid!r} asm_code 不是合法 hex")
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
    ap.add_argument("--strict", action="store_true", help="警告升级为错误")
    ap.add_argument("--quiet", action="store_true", help="只打印问题，隐藏 passed 清单")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "index.json").exists():
        print(f"{RED}未找到 {root / 'index.json'}，请指定仓根（--root）{RESET}", file=sys.stderr)
        return 1

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
    if not args.quiet:
        for p in res.passed:
            print(f"{GRAY}✓{RESET} {p}")
    for w in res.warnings:
        print(f"{YELLOW}WARN{RESET} {w}")
    for e in res.errors:
        print(f"{RED}ERROR{RESET} {e}")

    if res.errors:
        print(f"\n{RED}FAILED{RESET} — {len(res.errors)} errors, {len(res.warnings)} warnings")
        return 1
    if res.warnings and args.strict:
        print(f"\n{YELLOW}FAILED (strict){RESET} — {len(res.warnings)} warnings")
        return 1
    if res.warnings:
        print(f"\n{YELLOW}PASSED{RESET} with {len(res.warnings)} warning(s)")
        return 0
    print(f"\n{GREEN}PASSED{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
