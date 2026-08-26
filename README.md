# Flypigs Plugins Registry

`Flypigs Cheat Modifier` 的官方插件市场源（**Plugin Spec v1.0**）。

PC 端 `Flypigs.GameModifier` 与 Android 端 `flypigs-remote` 启动后都自动拉取本仓库根 `index.json`，列出所有可用插件，点击安装即触发：

```
下载 zip → sha256 校验 → 解压到 <app_dir>/plugins/<plugin_id>/
```

> 本 README 是 **Plugin Spec v1.0 的单一信源**。所有新插件开发、发布、PR 评审，**只认这份规范**；如与 PC/Android 端代码或 `docs/` 有出入，以本 README 为准。

---

## 🔒 三条核心铁律（写插件前必读）

### 铁律 #1：插件扩展**不得**触发 PC / 手机端发版

- 所有修改项**如何显示、按什么顺序、显示哪些分组**，全部由插件自身的 `manifest.groups` 决定。
- 软件启动时读取 `manifest.groups`（**有序数组**），按它渲染「修改功能」页面的分组与顺序。
- **临时占位组**不要在 `groups` 里塞"打补丁"字符串；如果某 mod 暂时未分类，归到客户端兜底的 `其他` 组——`其他` 不应在产品插件的 manifest 里出现。
- 新增 / 删除 / 重命名分组、改任何分组顺序 → 只改 `manifest.groups`，**不需要改 PC / 手机端代码**。

### 铁律 #2：数据真实性 — 严禁 AI 编造作弊数据

- AOB、pointer、value、fn_label 等真实游戏内存 / 引擎调用数据，**必须来自真实游戏调试、可信开源源码、或 plugin author 人工验证**。
- **禁止**让 AI 模型"拍脑袋"给你一段看似像样的字节序列或偏移量。
- 失效时**只改 JSON / 配置文件**，不重编译桌面端核心或引擎 DLL。
- 校验脚本会拦截过明显的伪造（比如 `aob: "AA BB CC DD ?? EE"` 全是 `??` 之类的占位）。

### 铁律 #3：游戏元信息归 `game.json`，插件元信息归 `manifest.json`

- `game.json` 描述**游戏本身**（name / 厂商 / release_year / process 列表 / 支持平台 / 启动配置 / 主题色 / assets 路径）。
- `manifest.json` 描述**本插件**（id / engine / version / features / groups / launch 路径）。
- 客户端通过 `game.json` 渲染封面/标题/主题色；UI 不硬编码任何游戏信息——换游戏只动 `game.json`，不改客户端。
- `game.json` **是可选**的（旧插件无 `game.json` 时客户端回退到 `manifest` 字段），但**新插件强烈建议提供**。

---

## 🔍 校验脚本（PR 前必跑）

[`scripts/plugins-validate.py`](scripts/plugins-validate.py) 跨平台 Python 3（无第三方依赖），一站式校验：

```bash
# 校验整个仓（最常用）
python scripts/plugins-validate.py

# 校验单个插件
python scripts/plugins-validate.py plugins/<plugin_id>

# 严格模式：警告也升级为错误（用于发版前最后一道关）
python scripts/plugins-validate.py --strict

# 只看问题（隐藏 PASSED 清单）
python scripts/plugins-validate.py --quiet

# 显式指仓根（默认当前目录）
python scripts/plugins-validate.py --root .
```

校验项（FAIL = 不能 merge）：

| # | 项 | 失败级别 |
|---|---|---|
| 1 | `index.json` 合法 JSON + `schema_version=2` | ERROR |
| 2 | `index.json.plugins[]` 必填字段（id/name/download/sha256/groups）齐全 | ERROR |
| 3 | `plugins/<id>/manifest.json` 合法 + 必填（id/name/process/engine/version/features） | ERROR |
| 4 | `manifest.id == dir 名 == zip 文件名前缀` | ERROR |
| 5 | `manifest.version` 与 zip 文件名 `<id>-<ver>.zip` 后缀匹配 | ERROR |
| 6 | `index.json.plugins[i].sha256 == zip 实际 sha256` | ERROR |
| 7 | `index.json.plugins[i].size == zip 实际 size` | ERROR |
| 8 | `manifest.groups` 是有序数组、去重、≥1 项 | ERROR |
| 9 | **每条 `memory.mods[].group` 必须命中 `manifest.groups`**（归组铁律） | ERROR |
| 10 | `manifest.features_count` 等于 `memory.mods.length`（有 memory）或 `features.length`（无 memory） | WARN |
| 11 | `feature.fn_kind ∈ {button,checkbox,slider,input,select,multi_select}` | WARN |
| 12 | 非 `button` 的 `feature` 必须有 `fn_label` | ERROR |
| 13 | `feature.id` 在 `manifest.features[]` 内唯一 | ERROR |
| 14 | `game.json`（可选）：`id == dir 名`、`name 非空`、`process` 合法 | ERROR |
| 15 | zip 路径安全（无 `..` 越段、无控制字符） | ERROR |
| 16 | zip 内 `manifest.json` 与仓根 `manifest.json` **字节一致** | ERROR |
| 17 | zip 内无 `.bak` / `_v2.` / `.tmp` / `~$` 等残留 | WARN |
| 18 | `plugins/<id>/` 与 `index.json.plugins[]` 一一对应（无孤儿目录、无悬空条目） | ERROR |

退出码：`0` = 全过；`1` = 有 error；`2` = 仅 warning（`--strict` 下变 `1`）。

---

## 📁 目录结构

```
flypigs-plugins/
├── index.json                      # 仓根：所有可用插件清单（schema_version=2）
├── README.md                       # 本文件（Plugin Spec v1.0 单一信源）
├── scripts/
│   └── plugins-validate.py         # 校验脚本（PR 前必跑）
└── plugins/
    └── <plugin_id>/                # 每个插件一个子目录（id 与目录名严格一致）
        ├── manifest.json           # 插件元信息 + 功能清单 + groups 铁律字段
        ├── memory.json             # AOB / pointer / value_type / mod.group
        ├── game.json               # 游戏元信息（可选，强烈建议）
        ├── assets/                 # 游戏图标/封面临床床（可选）
        │   └── icon.png            #  客户端右上角加载这个作为游戏封面
        └── <plugin_id>-<version>.zip  # 可发布的 zip 包本体
```

### zip 内部结构

```
<plugin_id>-<version>.zip
├── manifest.json     # 必含，与仓根 plugins/<id>/manifest.json 字节一致
├── memory.json       # 必含（若有），同上
├── game.json         # 可选，同上
└── assets/icon.png   # 可选，PC 端 header 渲染游戏封面用
```

> ⚠️ **zip 内不打包 engine DLL**。引擎 DLL（C++ AdjWang port）一般留在主仓 `plugins/<id>/engine/`，避免每次插件更新都要重打 dll；zip 只装数据。

---

## ✏️ 从 0 写一个新插件（开发者 step-by-step）

按这 7 步走完所有 SOP，**不要跳**：

1. **填 `plugins/<id>/manifest.json`**（必填）
   - `id` = 目录名（已建立 `plugins/<id>/`）
   - `engine` ∈ { `ra2_pipe`, `memory_scan`, ... }（参考主仓已有的 engine 类型）
   - `engine_min` = 引擎 DLL 最低版本
   - `version` = semver `X.Y.Z`（**初版用 `0.1.0`**，别上来 `1.0.0`）
   - `groups`：按你设计的功能顺序写**有序数组**
2. **填 `plugins/<id>/memory.json`**（如适用）
   - `mods[].group` 必须命中 `manifest.groups`（**归组铁律**）
   - `aob` / `pointer_path` / `value_type` 必须来自真实调试，**禁止凭感觉**
3. **填 `plugins/<id>/game.json`**（强烈推荐）
   - 至少填 `name` / `process`；推荐把 `developer` / `release_year` / `theme` 都填上
   - `process` 可以是 string 或 string 数组（多 exe 都列上）
4. **打 zip**：
   ```bash
   cd plugins/<id>
   zip -r <id>-<version>.zip manifest.json memory.json game.json assets/ -x "*.bak" "*.tmp" "*~"
   ```
5. **算 sha256 + size**：
   ```bash
   sha256sum <id>-<version>.zip   # Git Bash
   certutil -hashfile <id>-<version>.zip SHA256   # Windows
   ls -la <id>-<version>.zip | awk '{print $5}'   # size in bytes
   ```
6. **更新仓根 `index.json.plugins[]`**：写入新条目的 `id/name/process/engine/version/sha256/size/groups/features_count`；仓根 `updated_at` 与 `index.plugins[i].updated_at` 都设当前 ISO 时间
7. **跑校验**：
   ```bash
   python scripts/plugins-validate.py --strict
   ```
   没 ERROR 才开始 PR。

---

## 📦 字段表

### `index.json` (schema_version = 2)

```json
{
  "schema_version": 2,
  "updated_at": "2026-08-25T22:30:00Z",
  "market_base": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/",
  "plugins": [
    {
      "id": "ra2_yr",
      "version": "1.1.0",
      "sha256": "492101056dc3…",
      "size": 3905,
      "download": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/plugins/ra2_yr/ra2_yr-1.1.0.zip",
      "name": "红色警戒2：尤里的复仇 (RA2 YR)",
      "game": "RA2 YR",
      "process": "gamemd.exe",
      "engine": "ra2_pipe",
      "engine_min": "1.0.0",
      "author": "Flypigs",
      "description": "RA2 YR 全功能作弊……",
      "icon": null,
      "min_app": "1.0.0",
      "groups": ["经济","战斗增益","建造","单位操作","战场控制","任务调速","阵营保护"],
      "features_count": 32,
      "updated_at": "2026-08-25T22:30:00Z"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | int | ✅ | 当前 = `2`；客户端发现不识别则忽略整份索引 |
| `updated_at` | ISO8601 | ✅ | 本次仓根更新时间（UI 显示「市场更新于 …」） |
| `market_base` | URL | ✅ | 所有 `download` 字段的基址（`download` 也可写完整 URL 覆盖） |
| `plugins[]` | array | ✅ | 插件条目 |
| `plugins[].id` | string | ✅ | 插件唯一 id（小写+下划线），对应目录名 + zip 名 |
| `plugins[].version` | semver | ✅ | 当前可用版本（必须与 zip 文件名后缀一致） |
| `plugins[].sha256` | hex | ✅ | **zip 的 sha256**，客户端会校验，不一致拒绝安装 |
| `plugins[].size` | int |  | zip 字节数 |
| `plugins[].download` | URL | ✅ | zip 直链；可写 `market_base + 相对路径` 或完整 URL |
| `plugins[].name` | string | ✅ | 显示名 |
| `plugins[].game` | string | ✅ | 游戏简称（用于卡片副标题，必须与 `manifest.game`/`game.short_name` 对齐） |
| `plugins[].process` | string |  | 主目标进程名（仅展示用，运行时以 `game.json.process` 为准） |
| `plugins[].engine` | string | ✅ | 引擎 id（如 `ra2_pipe` / `memory_scan`） |
| `plugins[].engine_min` | semver |  | 引擎 DLL 最低版本 |
| `plugins[].author` | string |  | 作者署名 |
| `plugins[].description` | string |  | 卡片描述（1-2 行，过长被截断） |
| `plugins[].icon` | URL / null |  | 图标直链；为 null 用默认 emoji |
| `plugins[].min_app` | semver |  | 客户端最低支持版本 |
| `plugins[].groups` | string[] | ✅ | **有序分组数组**（铁律 #1） |
| `plugins[].features_count` | int |  | 修改项数量（应等于 `memory.mods.length` 或 `manifest.features.length`） |
| `plugins[].updated_at` | ISO8601 |  | 本条目最近发布/更新时刻 |

### `manifest.json`

```json
{
  "id": "ra2_yr",
  "name": "红色警戒2：尤里的复仇 (RA2 YR)",
  "process": "gamemd.exe",
  "engine": "ra2_pipe",
  "version": "1.1.0",
  "engine_min": "1.0.0",
  "author": "Flypigs",
  "launch": "E:\\hongjingRA2\\RA2 2022",
  "description": "RA2 YR 全功能作弊……",
  "groups": ["经济","战斗增益","建造","单位操作","战场控制","任务调速","阵营保护"],
  "game": "RA2 YR",
  "features": [
    { "id": "apply",          "name": "应用修改",   "type": "button",   "fn_label": "Apply",           "fn_kind": "button" },
    { "id": "god",            "name": "上帝模式",   "type": "checkbox", "fn_label": "God",             "fn_kind": "checkbox" },
    { "id": "adjust_game_speed","name":"调整游戏速度","type":"slider",  "fn_label": "AdjustGameSpeed", "fn_kind": "slider" }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 与目录名 + zip 前缀严格一致 |
| `name` | string | ✅ | 显示名 |
| `process` | string | ✅ | 主进程名（运行时优先用 `game.json.process`，回退到此） |
| `engine` | string | ✅ | 引擎 id |
| `version` | semver | ✅ | 必须与 zip 文件名 `<id>-<ver>.zip` 一致 |
| `engine_min` | semver |  | 引擎 DLL 最低版本 |
| `author` | string |  | 作者 |
| `launch` | string |  | 游戏启动路径（PC 端「启动游戏」按钮据此拉起；可缺，省略则提示用户手动启动） |
| `description` | string |  | 卡片描述 |
| `groups` | string[] | ✅ | **有序分组数组**（铁律 #1） |
| `game` | string |  | 游戏简称；与 `game.json.short_name`/`name` 对齐 |
| `features` | array | ✅ | UI 控件清单（描述驱动，不是真实 mod） |
| `features[].id` | string | ✅ | 在本插件内唯一 |
| `features[].name` | string | ✅ | 显示名 |
| `features[].type` / `features[].fn_kind` | string | ✅ | 控件类型：`checkbox` / `button` / `slider` / `input` / `select` / `multi_select` |
| `features[].fn_label` | string | ✅ | 引擎内对应执行标签（`button` 可省） |

### `memory.json`

```json
{
  "mods": [
    { "id": "god", "name": "上帝模式", "group": "战斗增益", "module": "gamemd.exe",
      "aob": "8B 86 ?? ?? ?? ?? 85 C0 74", "base_offset": 0, "value_type": "byte",
      "frozen": true, "target_value": 1, "fn_label": "God", "fn_kind": "checkbox" },
    { "id": "input_money", "name": "加钱", "group": "经济", ..., "min_value": 0, "max_value": 9999999 },

    // v2.7 AutoAssembler：type=code_patch（AOB + 字节替换，禁用时还原）
    { "id": "demo_no_clip", "name": "穿墙", "type": "code_patch", "group": "游戏系统",
      "module": "JustCause3.exe",
      "aob": "48 8B ?? ?? ?? ?? ?? 48 85 ?? 74",
      "patch_offset": 5,
      "patch_bytes": "90 90",
      "value_type": "byte", "frozen": false, "target_value": 0 },

    // v2.7 AutoAssembler：type=code_inject（AOB + VirtualAllocEx + jmp hook）
    { "id": "demo_one_hit_kill_inject", "name": "一击必杀 (hook)", "type": "code_inject",
      "group": "战斗增益", "module": "JustCause3.exe",
      "aob": "48 8B ?? ?? ?? ?? ?? E8 ?? ?? ?? ?? 48 85",
      "hook_size": 5,
      "asm_code": "48 C7 44 24 ?? 00 00 00 00 C3"   /* 伪例：mov [rsp+...],0; ret */ }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mods[].id` | string | ✅ | 在本插件内唯一 |
| `mods[].name` | string | ✅ | 显示名 |
| `mods[].type` | string |  | **`value`(缺省) / `code_patch` / `code_inject`**（v2.7 字段，决定运行时路径） |
| `mods[].group` | string | ✅ | **必须命中 `manifest.groups` 中一项**（铁律 #1 + #3） |
| `mods[].module` | string |  | 主模块名（通常 = `process`） |
| `mods[].aob` | string |  | AOB 扫描特征（hex 字符串，`?` 通配）。type=code_inject **必填**（命中点 = hook 位置） |
| `mods[].base_offset` | int |  | 基址偏移 |
| `mods[].pointer_path` | int[] |  | 多级指针链（一般 `[]` 或 `[base_offset]`） |
| `mods[].value_type` | string |  | `int32`/`int64`/`float`/`double`/`byte` |
| `mods[].frozen` | bool |  | 写入后是否周期性 re-write（type=code_patch / code_inject 无需冻结） |
| `mods[].target_value` | any |  | 启用时一次性写入的值 |
| `mods[].fn_label` | string |  | 注入式引擎（`ra2_pipe`）的执行标签 |
| `mods[].fn_kind` | string |  | 引擎调用方式（`checkbox`/`button`/`slider`/`input`） |
| `mods[].min_value` / `mods[].max_value` | int |  | slider/input 类型的范围 |
| `mods[].patch_offset` | int | type=code_patch | AOB 命中后从偏移起替换（缺省 0） |
| `mods[].patch_bytes` | string | type=code_patch ✅ | 替换字节 hex；禁用时自动还原 |
| `mods[].hook_size` | int | type=code_inject | 在 AOB 命中位置覆盖的 jmp 指令字节大小（x86/x64 默认 5） |
| `mods[].asm_code` | string | type=code_inject ✅ | 注入到远端 shellcode 的 x86/x64 机器码 hex |
| `mods[].calling_conv` | string |  | 调用约定（`cdecl`/`stdcall`/`thiscall`/`fastcall`），v2.8+ 实现 |

### v2.7 三种 mod type 的语义与区别

| type | 运行时做了什么 | 禁用时做了什么 | 适用场景 |
|------|------|------|------|
| `value`（缺省） | AOB 命中 + 沿 pointer_path 解析 → 写入数值 | 从 active 移除（不主动还原内存） | 数值读写：血量/弹药/钱 |
| `code_patch` | AOB 命中 + 写入 patch_bytes | **自动写回原字节**（备份在 MemoryEngine._patches） | NOP 类简单补丁：跳过伤害判定、跳过冷却 |
| `code_inject` | VirtualAllocEx 分配远端 shellcode → asm_code + jmp_back → 写入 jmp hook 覆盖 5 字节 | **写回原字节 + VirtualFree shellcode** | 复杂 hook：拦截伤害、修改资源数、强制调速度 |

**约束**：
- type=code_patch：patch_offset + patch_bytes 必填，patch_bytes 必须是合法 hex
- type=code_inject：aob + hook_size + asm_code 必填，hook_size ∈ [5..32]（x86/x64 默认 5；ARM64 走其他路径）
- 两种类型都不支持 ModSet（slider/input），只能是 Enable/Disable 的开/关
- **AOB 必须来自真实游戏调试**，禁止 AI 编造——插件作者自负其责

### `game.json`（强烈推荐）

```json
{
  "id": "ra2_yr",
  "name": "红色警戒2：尤里的复仇",
  "short_name": "RA2 YR",
  "developer": "Westwood Studios",
  "publisher": "Electronic Arts",
  "release_year": 2001,
  "platform": "Windows",
  "process": ["gamemd.exe", "ra2md.exe"],
  "genre": ["strategy", "rts"],
  "support": { "windows": true, "x86": true, "x64": false },
  "launch": { "exe": "gamemd.exe", "args": "" },
  "theme": { "primary": "#E63946", "accent": "#FFB703" },
  "assets": { "cover": "assets/cover.jpg", "banner": "assets/banner.jpg", "icon": "assets/icon.png" }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 与目录名一致 |
| `name` | string | ✅ | 显示名 |
| `short_name` | string |  | 简称（与 `manifest.game` 对齐） |
| `developer` / `publisher` | string |  | 厂商 |
| `release_year` | int |  | 首发年份 |
| `platform` | string |  | 平台（`Windows`/`Linux`/`...`） |
| `process` | string \| string[] |  | 目标进程名列表（兼容 string 和 array） |
| `genre` | string[] |  | 分类标签（`strategy`/`rts`/`fps`/...） |
| `support.{windows,x86,x64}` | bool |  | 客户端支持矩阵 |
| `launch.{exe,args}` | string |  | 启动配置 |
| `theme.{primary,accent}` | hex |  | 主题色（PC 端 header 渲染用） |
| `assets.{cover,banner,icon}` | path |  | 仓根 `plugins/<id>/` 下的相对路径 |

---

## ✅ PR 评审 checklist

新插件 / 改插件的 PR，**最少**过这 7 关才合并：

1. [ ] `python scripts/plugins-validate.py --strict` 退出码 = 0
2. [ ] `manifest.groups` 顺序合理（按用户心智模型，不是字母序）
3. [ ] `memory.mods[].group` 全部命中 `manifest.groups`（validate 已卡，但 PR 上复述确认）
4. [ ] AOB / pointer / value_type 字段**有真实调试证据**（附 PR 描述或 commit message）
5. [ ] `index.json.plugins[i]` 字段齐全，`sha256 / size / updated_at` 已更新
6. [ ] zip 内 `manifest.json` 与仓根 `manifest.json` 字节一致（validate 已卡）
7. [ ] 如果加了 `game.json`：文件可以被客户端单独读取（即使 zip 内不含也能 work）

---

## 🚀 发布流程（手动，目前无 CI）

1. 上述 step-by-step 已填齐 + `validate.py --strict` 过
2. `git add plugins/<id>/ index.json && git commit -m "feat(<id>): ..." && git push`
3. 客户端：
   - **PC 端**：「设置 → 关于 → 检查更新」拉新 `index.json`，识别后弹「插件更新」卡片
   - **手机端**：「插件中心 → 插件市场」下拉刷新 / 重启 APP 即看到

---

## 🧭 与 PC 端、移动端的协作

| 行为 | PC 端 `Flypigs.GameModifier` | Android `flypigs-remote` |
|------|------------------------------|--------------------------|
| 拉市场 | 「插件中心 → 插件市场」tab 自动 GET `market_base + index.json` | 同 |
| 安装 | 点「安装」→ `download` → sha256 校验 → 解压到 `plugins/<id>/` | 点「安装到电脑」→ 走 `plugin.install` 协议让 PC 端代为下载安装 |
| 状态 | 卡片显示「未安装 / 已安装 vX / 可更新 X→Y」 | 同样显示，依赖 PC 端回包 |
| 分组渲染 | 直接读 `manifest.groups` 排序后渲染「修改功能」页面 | 直接读 `manifest.groups` 排序后渲染「修改功能」页面 |
| 游戏封面 | `game.json.assets.icon` 拉 `plugins/<id>/assets/icon.png`，加载失败回退 🎮 emoji | n/a（手机端不渲染封面） |

> **两端共用同一份 `index.json` 与同一套 `manifest.groups` 规则**——任何插件扩展都不需要改两端代码（铁律 #1）。

---

## 🛣 升级计划

- [ ] GitHub Actions CI 自动跑 `validate.py --strict`（防止 PR 漏校验）
- [ ] CI 自动生成 `index.json`（从 `plugins/*/` 扫盘，避免人工编辑漏字段）
- [ ] 增量 diff 接口（手机端首次拉全量，之后只拉 diff）
- [ ] 插件签名（zip 内置签名，PC 端校验作者公钥）
- [ ] 多版本号索引（同一插件保留多个历史版本）

---

## 📜 License

MIT
