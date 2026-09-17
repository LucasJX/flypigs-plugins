#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plugin Spec canonical schema — 唯一规则真源（AUD-026-B）。

plugin_lint.py 与 plugins-validate.py 都必须从本模块取规则，禁止各自维护一份，
保证同一份插件数据由两个 validator 得出**同一套结论**（AUD-026 验收项：
"两个 validator 结果一致"）。

覆盖的规则：
  - 引擎能力类（镜像主仓 EngineRegistry.Resolve()）：
      data_driven  : external_memory / memory / injected_pipe / jc3_injected / generic_injected
                     AOB/asm 由数据驱动校验（plugin_lint 全量跑），fn_label 与 RA2 协议无关，不要求。
      legacy_label : ra2_pipe / legacy_label
                     RA2 专用 fn_label 协议；fn_label 必填（button / protected_list 例外）。
      None         : 未知引擎 → 两个 validator 都按"能力未知"处理（警告 + 不阻断）。
  - fn_kind 合法集合（UI 渲染 + 校验共用，7 种）。
  - fn_label 必填规则（按能力类判定，而非 engine 字符串后缀——旧 plugins-validate 用
    endswith("_pipe") 把 data_driven 的 injected_pipe 误判为注入式，对 JC3 报 12 个假错误）。
  - features_count 规则（manifest.features_count == 主功能数，去备用后缀 _2/_alt/_备用）。
  - RA2 FnLabel 合法枚举（src/engines/ra2_yr/src/protocol/model.h::FnLabel，去 kInvalid/kCount）。

用法：
  from schema import resolve_engine_class, fn_label_required, expected_features_count, ...
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 引擎能力类
# --------------------------------------------------------------------------
ENGINE_ALIASES = {
    "external_memory": "data_driven",
    "memory": "data_driven",
    "injected_pipe": "data_driven",
    "jc3_injected": "data_driven",
    "generic_injected": "data_driven",
    "legacy_label": "legacy_label",
    "ra2_pipe": "legacy_label",
}


def resolve_engine_class(engine: str | None) -> str | None:
    """解析 engine 字段，返回能力类别（data_driven / legacy_label / None=未知）。"""
    if not engine:
        return None
    return ENGINE_ALIASES.get(engine)


# --------------------------------------------------------------------------
# fn_kind / fn_label
# --------------------------------------------------------------------------
# fn_kind 合法集合（前端 UI 渲染依据 + 两 validator 共用）。
VALID_FN_KIND = frozenset({
    "button", "checkbox", "slider", "input",
    "select", "multi_select", "protected_list",
})
# 无需单个 fn_label 的 kind：button 与 protected_list 走列表/特殊协议，
# 没有"单 label"语义（protected_list = model.h::MakeProtectedListEvent，label 为空合法）。
LABEL_OPT_OUT_KIND = frozenset({"button", "protected_list"})

# RA2 FnLabel 合法枚举（model.h::FnLabel，去除 kInvalid / kCount 元数据）。
VALID_FN_LABELS = frozenset({
    # Button
    "Apply", "IAMWinner", "DeleteUnit", "ClearShroud", "GiveMeABomb",
    "UnitLevelUp", "UnitSpeedUp", "FastBuild", "ThisIsMine",
    # Checkbox
    "God", "InstBuild", "UnlimitSuperWeapon", "InstFire", "InstTurn",
    "RangeToYourBase", "FireToYourBase", "FreezeGapGenerator",
    "SellTheWorld", "BuildEveryWhere", "AutoRepair", "SocialismMajesty",
    "MakeCapturedMine", "MakeGarrisonedMine", "InvadeMode", "UnlimitTech",
    "UnlimitFirePower", "InstChrono", "SpySpy", "SelectEnemy", "PauseGame",
    # Slider
    "AdjustGameSpeed",
})


def fn_label_required(fkind: str | None, engine: str | None) -> bool:
    """fn_label 是否必填。

    规则（AUD-026-B 定稿）：
      - 仅 legacy_label 能力类（ra2_pipe / legacy_label）要求 fn_label；
      - kind 属于豁免集（button / protected_list）时不要求；
      - data_driven / 未知引擎一律不要求（数据驱动引擎的 fn_label 与 RA2 协议无关）。
    """
    return (resolve_engine_class(engine) == "legacy_label"
            and (fkind or "") not in LABEL_OPT_OUT_KIND)


# --------------------------------------------------------------------------
# features_count 规则
# --------------------------------------------------------------------------
# 备用 mod / feature 的后缀：主集合去重后计入 features_count 与 1:1 对齐。
# 注：_3 与 _2 同类的编号备用（JC3 freeze_challenge_timer 有 base/_2/_3 三个实现变体）。
ALT_SUFFIXES = ("_2", "_3", "_alt", "_备用")


def is_alt_id(fid: str) -> bool:
    return any(fid.endswith(suf) for suf in ALT_SUFFIXES)


def main_feature_ids(features) -> list[str]:
    """从 manifest.features 取主功能 id（去备用后缀、去非对象/缺 id）。"""
    if not isinstance(features, list):
        return []
    return [
        f.get("id") for f in features
        if isinstance(f, dict) and f.get("id") and not is_alt_id(f.get("id", ""))
    ]


def expected_features_count(features) -> int:
    """features_count 应等于的期望值（主功能数）。"""
    return len(main_feature_ids(features))
