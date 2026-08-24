# Flypigs Plugins Registry

`Flypigs` Cheat Modifier 的插件市场源。PC 端 `GameModifier` 启动后会自动拉本仓库根目录的 `index.json`，列出所有可用插件；点击下载按钮触发 PC 端下载 zip → sha256 校验 → 解压到 `plugins/<plugin_id>/`。

## 目录结构

```
flypigs-plugins/
├── index.json         # 仓根：所有可用插件的清单（schema_version=1）
├── README.md          # 本文件
└── (未来) releases/   # 历史 releases 归档
```

每个插件发布为一个 zip 包（**不上传到本仓**，走 GitHub Releases），文件名格式：

```
<plugin_id>-<version>.zip
```

zip 内部结构：

```
ra2-yr-1.0.0.zip
├── manifest.json     # 插件清单（schema 详见下文）
├── icon.png          # 插件图标（可选）
├── engines/          # 引擎 DLL（可选）
│   └── flypigs_ra2.dll
├── mods/             # 每个 mod 一个 json
│   ├── money.json
│   └── god_mode.json
└── docs/             # 文档（可选）
    └── README.md
```

## manifest.json 字段（schema v1）

```json
{
  "id": "ra2-yr",
  "name": "红色警戒2",
  "version": "1.0.0",
  "author": "LucasJX",
  "game": {
    "name": "Red Alert 2",
    "process": ["gamemd.exe"]
  },
  "engine": {
    "min": "1.0",
    "arch": "x86"
  },
  "mods": ["money", "god_mode"],
  "capabilities": ["toggle", "slider", "multi_select", "select"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 插件唯一 id |
| `name` | string | ✅ | 显示名 |
| `version` | string | ✅ | semver |
| `author` | string |  | 作者 |
| `game.name` | string | ✅ | 游戏官方名 |
| `game.process` | string[] | ✅ | 目标进程名（用于检测运行 + 注入） |
| `engine.min` | string | ✅ | 依赖引擎最低版本 |
| `engine.arch` | string | ✅ | `x86` / `x64` |
| `mods` | string[] | ✅ | mod id 列表，对应 `mods/<id>.json` |
| `capabilities` | string[] |  | 此插件支持的 kind 子集 |

## index.json 字段（schema v1）

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-25T00:00:00Z",
  "plugins": [
    {
      "id": "ra2-yr",
      "name": "红色警戒2",
      "version": "1.0.0",
      "download_url": "https://github.com/LucasJX/flypigs-plugins/releases/download/v1.0.0/ra2-yr-1.0.0.zip",
      "sha256": "abc123...",
      "size_bytes": 12345,
      "min_app_version": "1.0.0",
      "engine_min": "1.0",
      "icon_url": "https://raw.githubusercontent.com/LucasJX/flypigs-plugins/main/icons/ra2-yr.png"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | int | ✅ | 当前 = 1 |
| `generated_at` | ISO8601 | ✅ | 生成时间 |
| `plugins[].id` | string | ✅ | 对应 manifest.id |
| `plugins[].name` | string | ✅ | 显示名 |
| `plugins[].version` | string | ✅ | semver |
| `plugins[].download_url` | URL | ✅ | zip 直链（GitHub Releases） |
| `plugins[].sha256` | hex string | ✅ | zip 的 sha256（**外置**，不在 manifest 里） |
| `plugins[].size_bytes` | int |  | zip 大小 |
| `plugins[].min_app_version` | semver |  | PC 端 GameModifier 最低版本 |
| `plugins[].engine_min` | semver |  | 引擎 DLL 最低版本 |
| `plugins[].icon_url` | URL |  | 插件图标直链 |

## 发布流程

1. 本地按上述结构打包 zip
2. 用 `sha256sum <plugin_id>-<version>.zip` 算 hash
3. 在 GitHub Releases 创建一个 release `v<version>`，上传 zip
4. **手动**更新仓根 `index.json`（目前无 CI），提交 PR 合并
5. PC 端 `GameModifier` 下次启动或点「检查更新」会拉新 `index.json`，看到新插件

未来升级计划：

- CI 自动生成 index.json（避免手工 PR）
- 增量 diff 接口（手机端用）
- 插件签名

## 协议文档

PC ↔ Mobile 同步协议详见 [LucasJX/flypigs-cheat-modifier/docs/ws-protocol.md](https://github.com/LucasJX/flypigs-cheat-modifier/blob/main/docs/ws-protocol.md)。

## License

MIT