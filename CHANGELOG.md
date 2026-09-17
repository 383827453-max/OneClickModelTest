# Changelog

本项目的所有重要变更都记录在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 计划中
- 英文 README
- PR 模板
- 多账号列表（当前导入多账号文件只载入第 1 个）

---

## [1.2.5] - 2026-09-18

### 变更 —— 导出/导入改用 sub2api 账号格式

v1.2.3 的自有配置格式（`{app, kind, config:{...}}`）与 sub2api 不兼容，
**导入 sub2api 导出的账号文件无法识别**。本次改为 sub2api 账号格式。

**导出**（文件名 `sub2api-account-YYYYMMDDHHMMSS.json`）：

```json
{
  "exported_at": "2026-09-18T01:58:21Z",
  "proxies": [],
  "accounts": [
    {
      "name": "福利生图",
      "platform": "openai",
      "type": "apikey",
      "credentials": {
        "api_key": "sk-...",
        "base_url": "https://api.apisaver.com"
      },
      "extra": {
        "openai_apikey_responses_websockets_v2_enabled": false,
        "openai_apikey_responses_websockets_v2_mode": "off",
        "openai_long_context_billing_enabled": false,
        "openai_responses_supported": true,
        "upstream_billing_probe_enabled": true,
        "upstream_billing_rate_sync_enabled": false
      },
      "concurrency": 10,
      "priority": 1,
      "rate_multiplier": 1,
      "auto_pause_on_expired": true
    }
  ]
}
```

字段映射：

| sub2api | 本工具 |
|---|---|
| `accounts[0].name` | 账号别名（日志里的「开始测试账号」） |
| `accounts[0].credentials.base_url` | BASE URL |
| `accounts[0].credentials.api_key` | API KEY |
| `accounts[0].concurrency` | 并发数 |
| `accounts[0].platform` | 固定 `openai` |
| `accounts[0].type` | 固定 `apikey` |

**导入**自动识别三种格式，无需手动选：

1. **sub2api 账号格式** `{accounts:[{name, credentials:{...}}]}`
2. 应用自有格式 `{config:{...}}`（v1.2.3 导出，仍兼容）
3. 裸配置（顶层直接是 `base_url` 等字段）

**多账号文件**：`accounts` 含多个账号时，载入第 1 个，
并在日志面板列出全部账号名（`平台/类型`），提示手动取舍。

### 变更（其他）

- 菜单项文字明确化：导出账号 JSON（sub2api 格式）/ 导入账号 JSON（自动识别格式）
- 剪贴板复制/粘贴同样使用 sub2api 格式

### 验证

- 新增 `tests/smoke_sub2api_io.py`（**52 项断言**）：
  - 导出结构与真实 sub2api 样本**逐键比对**（顶层 / account 键集一致，
    credentials / extra 为子集）
  - 用真实 sub2api 导出文件导入，校验 name / base_url / api_key / concurrency
  - 文件往返、多账号提示、类型容错、边界值（`concurrency: 9999` 夹到 32）
  - 旧格式向后兼容、剪贴板往返
- 更新 `smoke_config_io.py` 中断言旧导出格式的 4 处用例
- 累计 **128 项断言**（22 + 54 + 52）全通过

---

## [1.2.4] - 2026-09-18

### 修复

**恢复了从 exe 还原源码时丢失的上半区界面元素。**
初版还原是按字节码结构骨架重建的，逻辑正确但视觉细节缺失，
与原始程序界面不一致，本次补齐：

- **标题栏** — 增加应用图标（36px 矢量绘制）+ `API MODEL SCANNER` 副标题
  （此前只有纯文字 `v1.2.1`，无图标、无副标题）
- **连接配置区**由单行拥挤布局改为**三行**：
  - 第 1 行 `BASE URL`
  - 第 2 行 `API KEY`（含显隐按钮）
  - 第 3 行 `列表超时` / `测试超时` / `并发数` / `回复上限` + **「保存配置」按钮**
- **新增状态条** — `● 就绪 · 延迟 · 模型数 · 上次检测`，四个指标实时刷新
- **底部行**改为固定说明：`v1.2.4 · 配置与历史内置存储(注册表)，无外部文件 · F5 快捷检测`

### 变更

- 窗口尺寸 1000×820 → **1020×900**
- 主区域 `QSplitter` 比例由 3:2 改为 **1:3** —— 模型列表压缩到约 36%，
  日志面板占约 64%（列表可滚动，压缩不影响使用）
- 模型列表最小高度设为 90，允许被拖拽压缩
- 状态指示灯由标题栏移入状态条；底部行不再承担状态显示

### 配置

- `test_timeout` 独立输入框接入配置读写
  （此前该配置项存在但无 UI 控件，只能靠导入 JSON 修改）
- `save_config` / `_save_now` / `_apply_cfg_to_ui` 同步纳入 `test_timeout`

### 修复（其他）

- 单体测试结束时误报「批量测试完成 N/M 成功」
  —— 现单测结束只把状态复位为「就绪」
- QSS 编辑过程中产生的乱码颜色值已清除

### 验证

- 工具栏 6 个按钮几何复核：**无重叠、无溢出**，搜索框仍余 457px
- QSS 自检：颜色值合法、花括号配平 74/74、Qt 解析无告警
- 两套测试 **22/22 + 52/52** 全通过

---

## [1.2.3] - 2026-09-18

### 新增

- **配置一键导入 / 导出 JSON** —— 工具栏新增「配置 ▾」菜单，四项操作：
  - **导出配置为 JSON 文件** — 把当前全部设置写入一个 JSON，
    默认文件名 `一键测API-配置-YYYYMMDD.json`
  - **从 JSON 文件导入配置** — 选择文件后立即应用到界面并持久化
  - **复制配置到剪贴板** / **从剪贴板粘贴配置** — 换机器时最省事的搬法
  - **恢复默认配置** — 一键回到出厂设置

- 导出的 JSON 带自描述头，便于识别与他人分享：

  ```json
  {
    "app": "一键测API",
    "kind": "config",
    "version": "1.2.3",
    "exported_at": "2026-09-18 00:30:00",
    "note": "此文件包含 API Key，请妥善保管",
    "config": {
      "base_url": "http://localhost:8082/v1",
      "api_key": "sk-...",
      "timeout": 15,
      "test_concurrency": 3,
      "max_tokens": 64,
      "account_alias": "",
      "always_on_top": false,
      "show_log": true
    }
  }
  ```

- **导入容错** —— 兼容两种格式：上述 `{config:{...}}` 包装形式，
  以及**裸配置**（顶层直接是字段）。逐字段校验类型：
  - 类型不符的字段丢弃（`timeout: "abc"`、`base_url: 123`）
  - 未知键忽略，不影响导入其余字段
  - 数字型字段接受数字字符串（`"77"` → `77`）
  - 布尔字段接受 `"true"/"1"/"yes"/"on"` 等写法
  - `base_url` 为空 → 整体拒绝，不覆盖当前配置
  - 无任何有效字段 → 拒绝并提示
- **导入来源识别** —— 非法 JSON、空剪贴板、剪贴板非 JSON 均有明确中文提示

### 修复

- `_save_now()` 未收集 `always_on_top`，导致导出/保存时置顶状态可能丢失
- `tests/smoke_v122.py` 断言 `APP_VERSION == "1.2.2"` 写死版本号，
  每次升版都会变红 —— 改为 `>=` 版本区间断言，并新增版本格式校验

### 验证

- 新增 `tests/smoke_config_io.py`（**52 项断言**）：payload 结构、
  文件导出/导入往返、裸配置、类型过滤、空值拒绝、
  剪贴板读写、恢复默认、按钮接线（真点一次按钮验证信号链）
- CI 由「跑单个测试文件」改为**自动遍历 `tests/smoke_*.py`**，
  新增测试无需改 workflow
- 测试内置 60 秒看门狗，防止模态对话框意外阻塞把 CI 挂死
- 累计 **74 项断言**（22 + 52）全通过

### 仓库

- 新增 Issue 模板：Bug 报告表单（14 字段）、功能建议表单（8 字段），
  并关闭空白 Issue 入口，引导至 README / CHANGELOG / Release

---

## [1.2.2] - 2026-09-18

### 新增

- **实时测试日志面板** — 窗口下半部分新增日志区（可拖拽分隔条调整高度），
  按步骤显示完整测试链路：`开始测试账号 → 账号类型 → 使用模型 →
  发送测试消息 → 已连接 → 响应正文 → 耗时`，用于确认模型是否真的回了话
- **响应正文回显** — 单模型测试时逐行显示模型实际返回内容（含空响应提示），
  不再只看一个毫秒数
- **账号别名** — 日志可填账号别名，留空时自动回退显示 BASE URL 主机名
- **批量模式摘要** — 批量测试只在日志里打一行「模型 + 首行响应 + 耗时」，
  不展开正文，避免刷屏
- **回复上限可调** — 新增 `max_tokens` 输入框（1–8192，默认 64），
  测试请求由原来的固定 `max_tokens: 1` 改为用户可调
- **日志开关** — 工具栏「日志」按钮可显示 / 隐藏日志面板，状态持久化

### 修复

- 非标准网关的响应解析：`choices[0].message.content` / `choices[0].text`
  之外，额外兼容 `content` / `response` / `output_text` 扁平字段

### 界面

- 主区域改为垂直 `QSplitter`（模型列表 : 日志面板 = 3 : 2）
- 默认窗口尺寸 980×720 → 1000×820，最小尺寸 760×560 → 780×620
- 日志面板配色与主题一致（青色标签 / 绿色响应 / 红色失败），
  等宽字体 + 自定义滚动条

### 存储

- 新增配置项 `account_alias`、`max_tokens`、`show_log`，沿用注册表存储

### 验证

- 新增离屏冒烟测试 `tests/smoke_v122.py`（21 项断言：控件构建、
  单测/批量/失败/空响应四种日志链路、响应体解析分支、日志开关持久化、
  worker 接线），不联网、不写注册表

---

## [1.2.1] - 2026-09-15

从 PyInstaller 打包产物完整还原源码工程后的**首次公开发布**。

### 新增

- **一键检测** — `GET {BASE URL}/models` 拉取全部可用模型，支持任意 OpenAI 兼容接口
- **单模型测试** — `POST {BASE URL}/chat/completions` 测真实响应延迟（毫秒）
- **全部测试** — 按设定并发数批量测试，最大并发可调
- **搜索过滤** — 按模型 ID 实时过滤列表
- **复制** — 单条复制 / 一键复制全部模型 ID
- **导出** — CSV（表格）/ JSON（完整数据）/ TXT（纯模型 ID）三种格式
- **历史记录** — 每次检测自动落库，支持单条删除与一键清空，上限 200 条
- **窗口置顶** — 可切换置顶状态
- **快捷键** — `F5` 快速检测

### 界面

- 无边框窗口 + 自绘圆角霓虹描边（青色 `#00e5ff` × 紫色 `#a855f7`）
- 深色渐变底 + 网格纹理 + 径向辉光
- 自定义状态指示灯（就绪 / 检测中 / 成功 / 失败，带呼吸动画）
- 主按钮悬停高度动画，卡片式模型行
- 全局 QSS 主题，含 hover / pressed / disabled 全态

### 错误处理

对以下情况给出明确中文提示，不静默失败：

| 异常 | 提示 |
|------|------|
| `ConnectTimeout` | 连接超时（含目标地址、排查建议） |
| `ReadTimeout` | 读取超时 |
| `ConnectionError` | 连接失败 |
| `RequestException` | 请求异常（含原始异常信息） |
| 非 200 状态码 | HTTP 状态码 + 响应体片段（截断 800 字符） |
| 非法 JSON | 解析失败 + 响应体片段（截断 500 字符） |
| 缺少 `data` 字段 | 格式异常 + 原始 JSON 片段 |
| `401` / `403` | (API Key 无效或无权限) |
| `404` | (模型不存在或未部署) |
| `429` | (额度不足或触发限流) |

### 存储

- 配置与历史通过 `QSettings` 存入 Windows 注册表
  （`HKCU\Software\YiJianCeAPI\一键测API`），不产生外部文件
- 检测到旧版 `config.json` / `history.json` 时自动迁移并删除原文件

### 打包与发布

- PyInstaller 打包配置（`build.spec`），产物 `一键测模型.exe`
- GitHub Actions 自动构建：`Install → Syntax check → Build → Upload artifact`
- 构建产物校验：

  | 项 | 值 |
  |---|---|
  | 大小 | 52,190,352 字节 |
  | SHA256 | `38732ee0e04124737af6340c6cac43049b6ed10ec1f75326f6200a7df78ef0ff` |

### 已知限制

- **Release 资产名不支持非 ASCII 字符** — 上传 `一键测模型.exe` 时
  GitHub 服务端会强制归一化为 `default.exe`，故发布资产名为
  `OneClickModelTest-v1.2.1-windows-x64.exe`。
  程序运行后窗口标题与注册表键名仍为「一键测API」。

---

## 版本说明

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.2.2 | 2026-09-18 | 实时测试日志面板 / 响应回显 / 回复上限可调 |
| v1.2.1 | 2026-09-15 | 首次公开发布 |

---

## 版本号规则

- **主版本号** — 不兼容的 API 变更或存储格式变更
- **次版本号** — 向下兼容的功能新增
- **修订号** — 向下兼容的问题修复

---

[Unreleased]: https://github.com/383827453-max/OneClickModelTest/compare/v1.2.2...HEAD
[1.2.2]: https://github.com/383827453-max/OneClickModelTest/releases/tag/v1.2.2
[1.2.1]: https://github.com/383827453-max/OneClickModelTest/releases/tag/v1.2.1
