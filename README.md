# Flypigs Plugins Registry

`Flypigs Cheat Modifier` 的官方插件市场源（数据驱动）。

PC 端 `Flypigs.GameModifier` 与 Android 端 `flypigs-remote` 启动后都会自动拉取本仓库根目录的 `index.json`，列出所有可用插件，点击安装即触发：

```
下载 zip → sha256 校验 → 解压到 <app_dir>/plugins/<plugin_id>/
```

---

## 🔒 核心铁律：作弊内容分组必须在插件内容里直接分好

**禁止**把"修改项如何分组"的逻辑写进 PC / 手机端代码里——所有分组必须来自插件自身声明的 `groups` 字段，软件直接读取并按此顺序渲染。

- **唯一权威来源**：每个插件的 `manifest.json` 里的 `groups`（**有序数组**）。
- **作用**：
  - 决定「修改功能」页面的分组顺序与显示哪些分组；
  - 决定「插件市场」卡片里分组 chip 的展示与排序。
- **新增插件**无需修改 PC / 手机端代码——只要在 `manifest.json` / `index.json` 里正确声明 `groups`，软件就自动按它渲染。
- **临时占位组**（如新功能未分类）：不要在 `groups` 数组里塞字符串来"打补丁"。如果某条修改项暂时未分类，归到 `其他`；`其他` 是兜底组，不应在产品插件的 manifest 里出现。

> 这条铁律是为了让**插件作者 + 软件解耦**——任何插件扩展不需要 PC / 手机端发版。

---

## 📁 目录结构

```
flypigs-plugins/
├── index.json                           # 仓根：所有可用插件清单（schema_version=2）
├── README.md                            # 本文件
└── plugins/
    └── <plugin_id>/                     # 每个插件一个子目录
        ├── <plugin_id>-<version>.zip   # 可发布的 zip 包本体
        ├── manifest.json                # 插件清单（zip 内也会带一份）
        └── icon.png                     # 插件图标（可选）
```

> zip 不再走 GitHub Releases，而是直接放仓库 `plugins/<id>/` 下，由 `index.json.market_base + plugins/<id>/<id>-<ver>.zip` 拼出直链，省一次额外跳转。

### zip 内部结构

```
<plugin_id>-<version>.zip
├── manifest.json     # 插件清单（与目录里的 manifest.json 保持一致）
├── icon.png          # 插件图标（可选）
├── engines/          # 引擎 DLL（可选；多数插件不带，放主仓 plugins/<id>//engine/ 即可）
└── memory.json       # AOB/pointer/value_type 数据（可选；走数据驱动引擎时需要）
```

---

## 📦 index.json（schema_version = 2）

```json
{
  "schema_version": 2,
  "updated_at": "2026-08-25T14:00:00Z",
  "market_base": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/",
  "plugins": [
    {
      "id": "ra2_yr",
      "name": "红色警戒2：尤里的复仇 (RA2 YR)",
      "game": "RA2 YR",
      "process": "gamemd.exe",
      "engine": "ra2_pipe",
      "engine_min": "1.0.0",
      "version": "1.0.0",
      "author": "Flypigs",
      "description": "RA2 YR 全功能作弊：经济 / 战斗增益 / 建造 / 单位操作 / 战场控制 / 任务调速 / 阵营保护，共 32 项。",
      "icon": null,
      "download": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/plugins/ra2_yr/ra2_yr-1.0.0.zip",
      "sha256": "b9ce566d623a7afaf0448eff888a458f6feacdcff0d136207ffd66308453bf84",
      "size": 3449,
      "min_app": "1.0.0",
      "groups": ["经济", "战斗增益", "建造", "单位操作", "战场控制", "任务调速", "阵营保护"],
      "features_count": 32
    }
  ]
}
```

### 字段表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | int | ✅ | 当前 = `2`；客户端发现不识别就忽略整份索引 |
| `updated_at` | ISO8601 | ✅ | 本次更新的提交时间（用来给 UI 显示"市场更新于 …"） |
| `market_base` | URL | ✅ | 所有 `download` 字段的基址，**`download` 也可写完整 URL 覆盖** |
| `plugins[]` | array | ✅ | 插件条目 |
| `plugins[].id` | string | ✅ | 插件唯一 id（小写 + 下划线），对应目录名 + zip 名 |
| `plugins[].name` | string | ✅ | 显示名 |
| `plugins[].game` | string | ✅ | 游戏简称（用于卡片副标题） |
| `plugins[].process` | string | ✅ | 目标进程名（用于检测游戏是否运行） |
| `plugins[].engine` | string | ✅ | 引擎 id（如 `ra2_pipe` / `memory_scan`） |
| `plugins[].engine_min` | semver | ✅ | 引擎 DLL 最低版本 |
| `plugins[].version` | semver | ✅ | 当前可用版本 |
| `plugins[].author` | string |  | 作者署名 |
| `plugins[].description` | string |  | 卡片描述（1~2 行；过长会被截断） |
| `plugins[].icon` | URL / null |  | 图标直链；为 null 用默认 emoji |
| `plugins[].download` | URL | ✅ | zip 直链；可以是 `market_base + 相对路径`，也可以是完整 URL |
| `plugins[].sha256` | hex | ✅ | **zip 包的 sha256**，客户端会校验，**不一致拒绝安装** |
| `plugins[].size` | int |  | zip 大小（字节） |
| `plugins[].min_app` | semver |  | 客户端最低支持版本（低于此的客户端提示升级） |
| `plugins[].groups` | string[] | ✅ | **有序分组数组**（见上文铁律） |
| `plugins[].features_count` | int |  | 修改项数量（用于卡片"X 项功能"展示，可由 manifest 算出来） |

---

## 🧩 manifest.json（zip 内 + 仓内各放一份，保持一致）

```json
{
  "id": "ra2_yr",
  "name": "红色警戒2：尤里的复仇 (RA2 YR)",
  "process": "gamemd.exe",
  "engine": "ra2_pipe",
  "version": "1.0.0",
  "engine_min": "1.0.0",
  "author": "Flypigs",
  "launch": "E:\\hongjingRA2\\RA2 2022",
  "description": "RA2 YR 全功能作弊：经济 / 战斗增益 / 建造 / 单位操作 / 战场控制 / 任务调速 / 阵营保护，共 32 项。",
  "groups": ["经济", "战斗增益", "建造", "单位操作", "战场控制", "任务调速", "阵营保护"],
  "game": "RA2 YR",
  "features": [
    { "id": "apply",          "name": "应用修改",       "type": "button",   "fn_label": "Apply",          "fn_kind": "button" },
    { "id": "god",            "name": "上帝模式",       "type": "checkbox", "fn_label": "God",            "fn_kind": "checkbox" },
    { "id": "adjust_game_speed", "name": "调整游戏速度", "type": "slider",   "fn_label": "AdjustGameSpeed","fn_kind": "slider" }
  ]
}
```

### 字段表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 与 `index.json` 一致 |
| `name` | string | ✅ | 显示名 |
| `process` | string | ✅ | 目标进程名 |
| `engine` | string | ✅ | 引擎 id |
| `version` | semver | ✅ | 必须与 zip 文件名 `<id>-<ver>.zip` 一致 |
| `engine_min` | semver | ✅ | 依赖引擎最低版本 |
| `author` | string |  | 作者 |
| `launch` | string |  | 游戏启动路径（PC 端注入器用它拉起游戏，可选） |
| `description` | string |  | 卡片描述 |
| `groups` | string[] | ✅ | **有序分组数组**——决定"修改功能"页面的分组顺序 |
| `game` | string | ✅ | 游戏简称 |
| `features` | array | ✅ | 修改项列表；`features_count = features.length` |
| `features[].id` | string | ✅ | 修改项唯一 id（在插件内） |
| `features[].name` | string | ✅ | 显示名 |
| `features[].type` / `features[].fn_kind` | string | ✅ | 控件类型：`checkbox` / `button` / `slider` / `input` / `multi_select` / `select` |
| `features[].fn_label` | string | ✅ | 引擎内对应的执行标签 |

> **`groups` 是有序的**——数组顺序就是 UI 显示顺序。如果客户端发现某条 `feature` 不在 `groups` 里，会归到 `其他` 兜底组并打 warning log。

---

## 🚀 发布流程（手动，目前无 CI）

1. 本地按上述结构整理 `<plugin_id>/<plugin_id>-<version>.zip`（zip 内带 `manifest.json` + 可选 `icon.png` / `engines/` / `memory.json`）
2. 算出 zip 的 sha256：
   ```bash
   sha256sum <plugin_id>-<version>.zip     # Git Bash
   certutil -hashfile <plugin_id>-<version>.zip SHA256   # CMD/PowerShell
   ```
3. 同步更新**两份** `manifest.json`：
   - 仓根 `plugins/<plugin_id>/manifest.json`
   - zip 内的 `manifest.json`（解开 zip 重打）
4. 更新仓根 `index.json`：在 `plugins[]` 末尾追加 / 替换对应条目，**字段顺序不重要但字段必填**，写入新的 `sha256` / `size` / `updated_at`
5. `git add plugins/<plugin_id>/ index.json && git push`
6. 客户端：
   - **PC 端**：下次启动或点「检查更新」会拉新 `index.json`，识别后弹"插件更新"卡片
   - **手机端**：进入「插件市场」tab，下拉刷新 / 重启 app 即看到新插件

---

## 🧪 校验

发布前本地一次过：

```bash
# 1. zip 完整性
unzip -t plugins/<plugin_id>/<plugin_id>-<version>.zip

# 2. sha256 与 index.json 一致
sha256sum plugins/<plugin_id>/<plugin_id>-<version>.zip
grep '"sha256":' index.json

# 3. manifest.json / index.json 是合法 JSON
python -m json.tool plugins/<plugin_id>/manifest.json
python -m json.tool index.json

# 4. groups 排序与 features 中实际出现的一致
python -c "import json;m=json.load(open('plugins/<plugin_id>/manifest.json'));print('groups:', m['groups']);print('feat count:', len(m['features']))"
```

---

## 🧭 与 PC 端、移动端的协作

| 行为 | PC 端 `Flypigs.GameModifier` | Android `flypigs-remote` |
|------|------------------------------|--------------------------|
| 拉市场 | 「插件中心 → 插件市场」tab 自动 GET `market_base + index.json` | 同 |
| 安装 | 点「安装」→ 走 `download` URL → sha256 校验 → 解压到 `plugins/<id>/` | 点「安装到电脑」→ 走 `plugin.install` 协议，让 PC 端代为下载安装 |
| 状态 | 卡片显示"未安装 / 已安装 vX / 可更新 X→Y" | 同样显示，依赖 PC 端回包 |
| 分组渲染 | 直接读 `manifest.groups` 排序后渲染「修改功能」页面 | 直接读 `manifest.groups` 排序后渲染「修改功能」页面 |

> 两端**共用同一份 `index.json` 与同一套 `manifest.groups` 规则**——任何插件扩展都不需要改两端代码。

---

## 🛣 升级计划

- [ ] CI 自动生成 `index.json`（避免手工 PR 漏填字段）
- [ ] 增量 diff 接口（手机端首次拉全量，之后只拉 diff）
- [ ] 插件签名（zip 内置签名，PC 端校验作者公钥）

---

## 📜 License

MIT