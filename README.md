# Flypigs Plugins Registry

`Flypigs Cheat Modifier` 的官方插件市场源（**Plugin Spec v1.1**）。

PC 端 `Flypigs.GameModifier` 与 Android 端 `flypigs-remote` 启动后自动拉取本仓库根 `index.json`，点击安装即触发：

```
下载 zip → sha256 校验 → Zip Slip 防护 → 解压到 <app_dir>/plugins/<plugin_id>/
```

> 本 README 是 **Plugin Spec 的单一信源**。所有新插件开发、发布、PR 评审，只认这份规范。

---

## 三条核心铁律

### 铁律 #1：插件扩展不得触发客户端发版

- 所有修改项的显示、顺序、分组，全部由插件自身的 `manifest.groups`（有序数组）决定。
- 新增/删除/重命名分组 → 只改 `manifest.groups`，不需要改 PC / 手机端代码。
- 未分类的 mod 归客户端兜底组 `其他`，但产品插件的 manifest 里不应出现 `其他`。

### 铁律 #2：数据真实性 — 严禁 AI 编造作弊数据

- AOB、pointer、value、fn_label、asm_code 等真实游戏数据，必须来自真实游戏调试、可信开源源码或人工验证。
- 禁止让 AI 模型"拍脑袋"给字节序列或偏移量。
- 失效时只改 JSON / 配置文件，不重编译客户端或引擎 DLL。

### 铁律 #3：游戏元信息归 game.json，插件元信息归 manifest.json

- `game.json` 描述游戏本身（name / 厂商 / process 列表 / 主题色 / assets）。
- `manifest.json` 描述本插件（id / engine / version / features / groups）。
- UI 不硬编码任何游戏信息，换游戏只动 `game.json`。

---

## 引擎类型

主仓采用**双引擎并存不合并**架构，分界线是变更频率：

| engine 字段 | 能力类别 | 适用游戏 | 数据格式 | 说明 |
|---|---|---|---|---|
| `ra2_pipe` | `legacy_label` | RA2 等老游戏 | fn_label 编译死 | DLL 内含真实作弊逻辑，20 年不变，编译进 DLL 最可靠 |
| `jc3_injected` | `injected_pipe` (data_driven) | JC3 等新游戏 | JSON 全量 AOB/asm/cave | DLL 是通用执行器，AOB/asm 随游戏版本频繁变动，数据驱动才能热更新 |
| `memory` / `generic_injected` | `injected_pipe` (data_driven) | 同上 | 同上 | 别名，等价于 `jc3_injected` |
| `external_memory` | `injected_pipe` (data_driven) | 外部式读写 | 同上 | 别名 |

`plugin_lint.py` 按能力类别校验：`legacy_label` 跳过 AOB/asm 校验（走 fn_label），`data_driven` 跑完整 AOB/asm/cave 校验。未知 engine 直接报错拒绝。

---

## 目录结构

```
flypigs-plugins/
├── index.json                      # 仓根：所有可用插件清单（schema_version=2）
├── README.md                       # 本文件（Plugin Spec 单一信源）
├── scripts/
│   ├── plugin_lint.py              # 插件数据校验（引擎能力分类 + AOB/asm + 合规红线）
│   └── plugins-validate.py         # 仓级一站式校验（index.json + zip + 目录一致性）
└── plugins/
    └── <plugin_id>/                # 每个插件一个子目录（id 与目录名严格一致）
        ├── manifest.json           # 插件元信息 + 功能清单 + groups
        ├── memory.json             # AOB / pointer / asm_code / mod.group
        ├── game.json               # 游戏元信息（可选，强烈建议）
        ├── assets/                 # 游戏图标（可选，SGDB 自动拉取）
        └── <plugin_id>-<version>.zip  # 可发布的 zip 包
```

### zip 内部结构

```
<plugin_id>-<version>.zip
├── manifest.json     # 必含，与仓根字节一致
├── memory.json       # 必含，同上
├── game.json         # 可选，同上
└── assets/icon.png   # 可选（通常不打包，由 SGDB 自动拉取）
```

> zip 内**不打包 engine DLL**。引擎 DLL 留主仓，避免每次插件更新都重打 DLL。

---

## 从 0 写一个新插件（7 步）

1. **填 `plugins/<id>/manifest.json`**
   - `id` = 目录名
   - `engine` 参考上方引擎类型表
   - `version` = semver（初版用 `0.1.0`）
   - `groups`：按用户心智模型写有序数组

2. **填 `plugins/<id>/memory.json`**
   - `mods[].group` 必须命中 `manifest.groups`（归组铁律）
   - AOB / asm_code / pointer 必须来自真实调试

3. **填 `plugins/<id>/game.json`**（强烈推荐）
   - 至少填 `name` / `process`；推荐填 `developer` / `release_year` / `theme` / `sgdb_game_id`

4. **打 zip**
   ```bash
   cd plugins/<id>
   zip -r <id>-<version>.zip manifest.json memory.json game.json -x "*.bak" "*.tmp"
   ```

5. **算 sha256 + size**
   ```bash
   certutil -hashfile <id>-<version>.zip SHA256   # Windows
   ```

6. **更新仓根 `index.json.plugins[]`**：写入 id/name/engine/version/sha256/size/groups/features_count/sgdb_game_id/download

7. **跑校验**
   ```bash
   python scripts/plugin_lint.py plugins/<id>/memory.json --engine <engine>
   python scripts/plugins-validate.py --strict
   ```

---

## 字段表

### index.json (schema_version = 2)

```json
{
  "schema_version": 2,
  "updated_at": "2026-09-02T12:00:00Z",
  "market_base": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/",
  "plugins": [
    {
      "id": "just_cause_3",
      "version": "1.1.2",
      "sha256": "24b974e9...",
      "size": 5591,
      "download": "https://api.github.com/repos/LucasJX/flypigs-plugins/contents/plugins/just_cause_3/just_cause_3-1.1.2.zip",
      "name": "正当防卫3 (Just Cause 3)",
      "game": "JC3",
      "process": "JustCause3.exe",
      "engine": "jc3_injected",
      "engine_min": "1.0.0",
      "author": "Flypigs",
      "description": "全功能修改器：角色/武器/载具/抓钩/游戏系统",
      "min_app": "1.0.0",
      "groups": ["角色","武器","载具","抓钩装备","游戏系统"],
      "features_count": 16,
      "updated_at": "2026-09-01T11:48:26Z",
      "sgdb_game_id": 2403
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int | ✅ | 当前 = `2` |
| `updated_at` | ISO8601 | ✅ | 仓根更新时间 |
| `market_base` | URL | ✅ | download 基址 |
| `plugins[].id` | string | ✅ | 唯一 id（小写+下划线），= 目录名 = zip 前缀 |
| `plugins[].version` | semver | ✅ | 与 zip 文件名后缀一致 |
| `plugins[].sha256` | hex | ✅ | zip 的 sha256，客户端强制校验 |
| `plugins[].size` | int | | zip 字节数 |
| `plugins[].download` | URL | ✅ | zip 直链。**推荐用 `api.github.com/repos/.../contents/`**（raw 域在国内部分出口被拦截） |
| `plugins[].name` | string | ✅ | 显示名 |
| `plugins[].game` | string | ✅ | 游戏简称 |
| `plugins[].process` | string | | 主进程名（展示用，运行时以 game.json 为准） |
| `plugins[].engine` | string | ✅ | 引擎 id（见引擎类型表） |
| `plugins[].engine_min` | semver | | 引擎 DLL 最低版本 |
| `plugins[].author` | string | | 作者 |
| `plugins[].description` | string | | 卡片描述 |
| `plugins[].min_app` | semver | | 客户端最低版本 |
| `plugins[].groups` | string[] | ✅ | 有序分组数组（铁律 #1） |
| `plugins[].features_count` | int | | 修改项数量 |
| `plugins[].updated_at` | ISO8601 | | 本条目更新时刻 |
| `plugins[].sgdb_game_id` | int | | SteamGridDB game_id，PC 端首次安装自动拉真海报（强烈建议填） |

### manifest.json

```json
{
  "id": "just_cause_3",
  "name": "正当防卫3 (Just Cause 3)",
  "process": "JustCause3.exe",
  "engine": "jc3_injected",
  "version": "1.1.2",
  "engine_min": "1.0.0",
  "author": "Flypigs",
  "launch": "C:\\Games\\Just Cause 3\\JustCause3.exe",
  "description": "全功能修改器",
  "groups": ["角色","武器","载具","抓钩装备","游戏系统"],
  "game": "JC3",
  "features": [
    { "id": "god", "name": "无敌", "type": "checkbox", "fn_label": "God", "fn_kind": "checkbox" }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | = 目录名 = zip 前缀 |
| `name` | string | ✅ | 显示名 |
| `process` | string | ✅ | 主进程名（运行时优先用 game.json.process） |
| `engine` | string | ✅ | 引擎 id（见引擎类型表） |
| `version` | semver | ✅ | = zip 文件名 `<id>-<ver>.zip` |
| `engine_min` | semver | | 引擎 DLL 最低版本 |
| `author` | string | | 作者 |
| `launch` | string | | 游戏启动路径（PC 端「启动游戏」按钮） |
| `description` | string | | 卡片描述 |
| `groups` | string[] | ✅ | 有序分组数组 |
| `game` | string | | 游戏简称 |
| `features` | array | ✅ | UI 控件清单 |
| `features[].id` | string | ✅ | 插件内唯一 |
| `features[].name` | string | ✅ | 显示名 |
| `features[].fn_kind` | string | ✅ | `checkbox`/`button`/`slider`/`input`/`select`/`multi_select` |
| `features[].fn_label` | string | ✅ | 引擎执行标签（button 可省） |

### memory.json

```json
{
  "mods": [
    {
      "id": "infinite_health",
      "name": "无限生命",
      "group": "角色",
      "type": "code_inject",
      "module": "JustCause3.exe",
      "aob": "48 8B ?? ?? ?? ?? ?? 48 85 ?? 74",
      "hook_size": 7,
      "asm_code": "push rax\nmov rax,[health]\nmov dword ptr [rax],999\npop rax",
      "aob_vars": { "health": { "offset": 4, "size": 8 } },
      "aob_refs": {},
      "flags": ["health"],
      "flag": "health",
      "conflicts": []
    },
    {
      "id": "max_money",
      "name": "最大金钱",
      "group": "游戏系统",
      "type": "value",
      "module": "JustCause3.exe",
      "aob": "8B 86 ?? ?? ?? ?? 85 C0 74",
      "pointer_path": [0],
      "value_type": "int32",
      "frozen": true,
      "target_value": 9999999
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mods[].id` | string | ✅ | 插件内唯一 |
| `mods[].name` | string | ✅ | 显示名 |
| `mods[].type` | string | | `value`(缺省) / `code_patch` / `code_inject` |
| `mods[].group` | string | ✅ | 必须命中 manifest.groups |
| `mods[].module` | string | | 主模块名 |
| `mods[].aob` | string | | AOB 扫描特征（hex，`?` 通配）。code_inject 必填 |
| `mods[].pointer_path` | int[] | | 多级指针链 |
| `mods[].value_type` | string | | `int32`/`int64`/`float`/`double`/`byte` |
| `mods[].frozen` | bool | | 写入后是否周期重写（code_patch/code_inject 不需要） |
| `mods[].target_value` | any | | 启用时写入的值 |
| `mods[].fn_label` | string | | legacy_label 引擎的执行标签 |
| `mods[].patch_offset` | int | code_patch | AOB 命中后偏移起替换（缺省 0） |
| `mods[].patch_bytes` | string | code_patch ✅ | 替换字节 hex，禁用时自动还原 |
| `mods[].hook_size` | int | code_inject | jmp hook 覆盖字节数（x64 默认 5，范围 5-32） |
| `mods[].asm_code` | string | code_inject ✅ | **汇编文本**（非 hex），支持 `{var}` 占位符 |
| `mods[].aob_vars` | object | | AOB 命中处提取的变量：`{name: {offset, size}}` |
| `mods[].aob_refs` | object | | AOB 命中处的引用地址 |
| `mods[].flags` | string[] | | 共享变量区 flag 变量名（按名分配） |
| `mods[].flag` | string | | 主 flag 变量名 |
| `mods[].conflicts` | string[] | | 互斥 mod id 列表（双向声明） |

#### asm_code 占位符规则

`asm_code` 是**汇编文本**（由主仓 AsmHelper 编码为机器码），支持以下占位符：

- `{var_name}` — 来自 `aob_vars` 的变量，替换为从 AOB 命中处提取的绝对地址
- `{flag_name}` — 共享变量区 flag 变量，替换为运行时分配的地址
- 寄存器直接写 `rax`/`rcx` 等，不需要占位符

示例：
```asm
push rax
mov rax,[health]        ; {health} 来自 aob_vars
mov dword ptr [rax],999
pop rax
```

#### 三种 mod type 语义

| type | 启用时 | 禁用时 | 适用场景 |
|---|---|---|---|
| `value` | AOB + pointer → 写数值 | 从 active 移除 | 血量/弹药/钱 |
| `code_patch` | AOB 命中 → 写 patch_bytes | 自动写回原字节 | NOP 类简单补丁 |
| `code_inject` | 分配 cave → 写 asm_code + jmp_back → 5 字节 hook | 写回原字节 + 释放 cave | 复杂 hook |

### game.json（强烈推荐）

```json
{
  "id": "just_cause_3",
  "name": "正当防卫3",
  "short_name": "JC3",
  "developer": "Avalanche Studios",
  "publisher": "Square Enix",
  "release_year": 2015,
  "platform": "Windows",
  "process": ["JustCause3.exe"],
  "theme": { "primary": "#E63946", "accent": "#FFB703" },
  "sgdb_game_id": 2403
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | = 目录名 |
| `name` | string | ✅ | 显示名 |
| `short_name` | string | | 简称 |
| `developer` / `publisher` | string | | 厂商 |
| `release_year` | int | | 首发年份 |
| `process` | string \| string[] | | 目标进程名（支持多 exe） |
| `theme.{primary,accent}` | hex | | 主题色 |
| `sgdb_game_id` | int | | SteamGridDB game_id（PC 端自动拉真海报） |

---

## 校验脚本

### plugin_lint.py — 插件数据校验

```bash
# 校验单个 memory.json（需指定 engine）
python scripts/plugin_lint.py plugins/<id>/memory.json --engine jc3_injected

# 传入 manifest 跑完整校验（含合规红线、fn_label 枚举、跨 provider 检查）
python scripts/plugin_lint.py plugins/<id>/memory.json --engine jc3_injected --manifest plugins/<id>/manifest.json
```

校验规则：

| 类别 | 规则 |
|---|---|
| 引擎分类 | 按 engine 能力类别（data_driven / legacy_label）选择校验路径，未知 engine 报错 |
| 必备字段 | id/name/group 必填，type 合法 |
| 归组铁律 | mods[].group 必须命中 manifest.groups |
| AOB 校验 | data_driven 引擎：aob 合法 hex、非全 `?`、code_inject 必填 |
| asm 校验 | code_inject：asm_code 非空、占位符在 aob_vars/aob_refs/flags 中声明 |
| hook_size | code_inject：hook_size ∈ [5, 32] |
| patch_bytes | code_patch：合法 hex、非空 |
| conflicts | 双向声明校验（A→B 必须 B→A） |
| 合规红线 | online=true / anticheat 字段等 → 拒绝（防联机作弊） |
| fn_label | legacy_label 引擎：fn_label 必须在合法枚举内 |
| 跨 provider | mod.engine 与 manifest.engine 能力不同 → 拒绝 |

### plugins-validate.py — 仓级校验

```bash
python scripts/plugins-validate.py --strict
```

校验项（23 项）：index.json 合法性、zip sha256/size 一致性、manifest 与 zip 字节一致、目录与 index 一一对应、归组铁律、AutoAssembler 字段、sgdb_game_id 一致性等。

退出码：`0` = 全过；`1` = 有 error；`2` = 仅 warning（--strict 下变 1）。

---

## PR 评审 checklist

1. `python scripts/plugin_lint.py ...` + `python scripts/plugins-validate.py --strict` 退出码 = 0
2. `manifest.groups` 顺序合理（按用户心智模型）
3. `memory.mods[].group` 全部命中 `manifest.groups`
4. AOB / asm_code / pointer 有真实调试证据（附 PR 描述）
5. `index.json.plugins[i]` 字段齐全，sha256/size/updated_at 已更新
6. download URL 推荐用 `api.github.com/repos/.../contents/`（非 raw 域）
7. 新插件填了 `sgdb_game_id`，且**没把 assets/icon.png 打进 zip**
8. asm_code 中的占位符全部在 aob_vars/aob_refs/flags 中声明

---

## 已上架插件

| 插件 | 版本 | 引擎 | 功能数 | sgdb_game_id |
|---|---|---|---|---|
| ra2_yr（红色警戒2：尤里的复仇） | 1.1.1 | ra2_pipe (legacy_label) | 31 | 38629 |
| just_cause_3（正当防卫3） | 1.1.2 | jc3_injected (data_driven) | 16 | 2403 |

---

## v2.8 海报自动拉取 SOP

1. 打开 https://www.steamgriddb.com/ 搜游戏名
2. 查 game_id：`curl -H "Authorization: Bearer KEY" 'https://www.steamgriddb.com/api/v2/search/autocomplete/<name>'`
3. 填进 `game.json` 和 `index.json.plugins[]` 的 `sgdb_game_id`
4. **不要打包 assets/icon.png** — PC 端首次安装自动拉 600x900 真海报
5. SGDB key 从 `~/.flypigs/sgdb.key` 或环境变量 `FLYPIGDB_KEY` 读取，**绝不入源码**

---

## 升级计划

- [ ] GitHub Actions CI 自动跑校验
- [ ] CI 自动生成 index.json
- [ ] 增量 diff 接口
- [ ] 插件签名
- [ ] 多版本号索引

---

## License

MIT
