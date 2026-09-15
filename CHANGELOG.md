# Changelog

本项目的所有重要变更都记录在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 新增
- Issue 模板：Bug 报告表单、功能建议表单，并关闭空白 Issue 入口

### 计划中
- 英文 README
- PR 模板
- 单元测试（config 读写、错误分类、模型列表归一化）

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
| v1.2.1 | 2026-09-15 | 首次公开发布 |

---

## 版本号规则

- **主版本号** — 不兼容的 API 变更或存储格式变更
- **次版本号** — 向下兼容的功能新增
- **修订号** — 向下兼容的问题修复

---

[Unreleased]: https://github.com/383827453-max/OneClickModelTest/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/383827453-max/OneClickModelTest/releases/tag/v1.2.1
