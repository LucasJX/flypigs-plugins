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

# --------------------------------------------------------------------------
# RA2 fn_label → 引擎事件类型（唯一真源）
# --------------------------------------------------------------------------
# 来源：src/engines/ra2_yr/src/backend/hook/trainer.cc 的 On*Event 分派。
#
# ⚠️ 不要以 protocol/model.h 的 enum 注释为准：那里把 kApply 标在 "// Button" 段，
# 但引擎实际走 OnInputEvent（写金钱），注释是误导性残留。
# 2026-10-21 实测：插件仓曾照着注释把「钱」写成 type=button，详情页就只渲染出
# 「触发」按钮、金额写死 —— 「触发功能却变成别的控件」这类错位的根因就在这里。
# 本表是插件数据声明 fn_kind 的唯一依据，由 plugins-validate 强制。
FN_LABEL_EVENT_KIND = {
    # OnInputEvent → WriteCredit(val)
    "Apply": "input",
    # OnButtonEvent（一次性动作，8）
    "IAMWinner": "button",
    "DeleteUnit": "button",
    "ClearShroud": "button",
    "GiveMeABomb": "button",
    "UnitLevelUp": "button",
    "UnitSpeedUp": "button",
    "FastBuild": "button",
    "ThisIsMine": "button",
    # OnCheckboxEvent（可开可关，21）
    "God": "checkbox",
    "InstBuild": "checkbox",
    "UnlimitSuperWeapon": "checkbox",
    "InstFire": "checkbox",
    "InstTurn": "checkbox",
    "RangeToYourBase": "checkbox",
    "FireToYourBase": "checkbox",
    "FreezeGapGenerator": "checkbox",
    "SellTheWorld": "checkbox",
    "BuildEveryWhere": "checkbox",
    "AutoRepair": "checkbox",
    "SocialismMajesty": "checkbox",
    "MakeCapturedMine": "checkbox",
    "MakeGarrisonedMine": "checkbox",
    "InvadeMode": "checkbox",
    "UnlimitTech": "checkbox",
    "UnlimitFirePower": "checkbox",
    "InstChrono": "checkbox",
    "SpySpy": "checkbox",
    "SelectEnemy": "checkbox",
    "PauseGame": "checkbox",
    # OnSliderEvent（1）
    "AdjustGameSpeed": "slider",
}

# RA2 权威中文名（唯一真源）
# 来源：src/engines/ra2_yr/src/archive/frontend/desktop/char_table.h
#   GetFnStrZh(FnLabel)   → 功能名
#   GetGuiStrZh(GuiLabel) → 界面文案（kMoney="钱"、kProtectedHouseList="保护阵营"）
# Apply 例外：功能名取「钱」（原 UI 里金额输入框旁的字段标签 kMoney），
# 动作按钮取「修改」（GetFnStrZh(kApply)）—— 原 trainer 里就是两处分开文案。
FN_LABEL_ZH_NAMES = {
    "Apply": "钱",
    "IAMWinner": "立即胜利",
    "DeleteUnit": "删除单位",
    "ClearShroud": "地图全开",
    "GiveMeABomb": "核弹攻击",
    "UnitLevelUp": "单位升级",
    "UnitSpeedUp": "单位加速",
    "FastBuild": "快速建造",
    "ThisIsMine": "这是我的",
    "God": "无敌",
    "InstBuild": "瞬间建造",
    "UnlimitSuperWeapon": "无限超武",
    "InstFire": "极速攻击",
    "InstTurn": "极速转身",
    "RangeToYourBase": "远程攻击",
    "FireToYourBase": "远程警戒",
    "FreezeGapGenerator": "瘫痪裂缝产生器",
    "SellTheWorld": "卖卖卖",
    "BuildEveryWhere": "随意建筑",
    "AutoRepair": "自动修理",
    "SocialismMajesty": "社会主义万岁",
    "MakeCapturedMine": "全是我的-工程师占领",
    "MakeGarrisonedMine": "全是我的-房屋驻军",
    "InvadeMode": "侵略模式",
    "UnlimitTech": "全科技",
    "UnlimitFirePower": "大量弹药-重新建造生效",
    "InstChrono": "瞬间超时空",
    "SpySpy": "无间道",
    "SelectEnemy": "多选敌方单位",
    "PauseGame": "暂停游戏",
    "AdjustGameSpeed": "任务调速",
}

# 阵营保护（protected_list）没有 fn_label，权威名单独登记
# （char_table.h GetGuiStrZh(GuiLabel::kProtectedHouseList)）。
PROTECTED_LIST_ZH_NAME = "保护阵营"

# --------------------------------------------------------------------------
# RA2 权威分组（唯一真源）
# --------------------------------------------------------------------------
# 来源：frontend/web/main.js 的 CATEGORY_OF（功能 → data-cat）
#     + frontend/web/index.html 的分组标题（data-cat → 中文标题）。
# 注意：AdjustGameSpeed 属于 battlefield（战场控制）—— 原 trainer 把它放在
# 战场控制分组底部的独立滑杆块里，**不是**单独一个「任务调速」分组。
RA2_GROUP_CATS = {
    "economy": "经济",
    "combat": "战斗增益",
    "build": "建造",
    "units": "单位操作",
    "battlefield": "战场控制",
    "filter": "阵营保护",
}

FN_LABEL_GROUP = {
    # economy（含页面顶部的金额输入块 Apply）
    "Apply": "economy",
    "SellTheWorld": "economy",
    "SocialismMajesty": "economy",
    # combat
    "God": "combat",
    "InstFire": "combat",
    "InstTurn": "combat",
    "RangeToYourBase": "combat",
    "FireToYourBase": "combat",
    "UnlimitFirePower": "combat",
    "UnlimitSuperWeapon": "combat",
    "InstChrono": "combat",
    # build
    "FastBuild": "build",
    "InstBuild": "build",
    "BuildEveryWhere": "build",
    "AutoRepair": "build",
    "UnlimitTech": "build",
    # units
    "UnitLevelUp": "units",
    "UnitSpeedUp": "units",
    "DeleteUnit": "units",
    "ThisIsMine": "units",
    "MakeCapturedMine": "units",
    "MakeGarrisonedMine": "units",
    "InvadeMode": "units",
    "SelectEnemy": "units",
    "SpySpy": "units",
    # battlefield
    "ClearShroud": "battlefield",
    "GiveMeABomb": "battlefield",
    "IAMWinner": "battlefield",
    "FreezeGapGenerator": "battlefield",
    "PauseGame": "battlefield",
    "AdjustGameSpeed": "battlefield",
}

# RA2 FnLabel 合法枚举 = 上面事件类型表的键集（单一真源，不再维护第二份清单）。
VALID_FN_LABELS = frozenset(FN_LABEL_EVENT_KIND)

# 可逆 mod 类型：禁用时能真正还原（code_patch 还原原字节 / code_inject 释放 cave）。
# 这类 mod 必须用开关（开/关），不能声明成一次性「触发」按钮 ——
# 否则用户点一次就再也关不掉（JC3 有 3 项曾被声明成 button，2026-10-21 修正）。
REVERSIBLE_MOD_TYPES = frozenset({"code_patch", "code_inject"})


def fn_label_event_kind(fn_label: str | None) -> str | None:
    """RA2 fn_label 对应的引擎事件类型（input/button/checkbox/slider），未知返回 None。"""
    if not fn_label:
        return None
    return FN_LABEL_EVENT_KIND.get(fn_label)


def authoritative_zh_name(fn_label: str | None, mod_id: str | None = None) -> str | None:
    """权威中文名。fn_label 命中映射则取映射；阵营保护（无 fn_label）走特例；否则 None。"""
    if fn_label:
        return FN_LABEL_ZH_NAMES.get(fn_label)
    if mod_id == "protected":
        return PROTECTED_LIST_ZH_NAME
    return None


def authoritative_group(fn_label: str | None, mod_id: str | None = None) -> str | None:
    """权威分组名（中文）。fn_label 命中映射则取映射；阵营保护走特例；否则 None。"""
    if fn_label:
        cat = FN_LABEL_GROUP.get(fn_label)
        if cat:
            return RA2_GROUP_CATS.get(cat)
    if mod_id == "protected":
        return RA2_GROUP_CATS["filter"]
    return None


def is_reversible_mod(mod_type: str | None) -> bool:
    """该 mod 是否可逆（禁用能还原）—— 决定它必须是开关而不是触发按钮。"""
    return (mod_type or "value").lower() in REVERSIBLE_MOD_TYPES


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
