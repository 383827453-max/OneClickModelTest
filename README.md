# 一键测API (OneClick Model Test)

一个**科技风深色 GUI 工具**，用于一键检测任意 **OpenAI 兼容接口**的可用模型列表，并逐个/批量测试模型的响应延迟。

> 版本 **v1.2.1** · Python 3.13 + PySide6 · Windows

---

## 下载

**免安装，双击即用**（无需 Python 环境）：

👉 [**OneClickModelTest-v1.2.1-windows-x64.exe**](https://github.com/383827453-max/OneClickModelTest/releases/latest)

| 项 | 值 |
|---|---|
| 大小 | 52,190,352 字节（约 49.8 MB） |
| SHA256 | `38732ee0e04124737af6340c6cac43049b6ed10ec1f75326f6200a7df78ef0ff` |
| 平台 | Windows x64 |

```powershell
# 下载后校验完整性
Get-FileHash .\OneClickModelTest-v1.2.1-windows-x64.exe -Algorithm SHA256
```

> 资产名为英文是因为 GitHub Release 不支持非 ASCII 文件名；
> 程序运行后窗口标题、注册表键名仍为「一键测API」。

---

## 功能

| 功能 | 说明 |
|------|------|
| 🔍 一键检测 | `GET {BASE URL}/models` 拉取全部可用模型 |
| ⚡ 单模型测试 | `POST {BASE URL}/chat/completions` 测真实响应时间（ms） |
| ⚡ 全部测试 | 按设定的**并发数**批量测，最大并发可调 |
| 🔎 搜索过滤 | 按模型 ID 实时过滤列表 |
| 📋 复制 | 单条复制 / 一键复制全部模型 ID |
| 💾 导出 | CSV（表格）/ JSON（完整数据）/ TXT（纯模型 ID） |
| 🕘 历史记录 | 每次检测自动落库，支持单条删除与一键清空 |
| 📌 窗口置顶 | 可切换置顶，无边框自绘标题栏 |
| ⌨️ 快捷键 | `F5` 快速检测 |

## 界面特性

- 无边框窗口 + 自绘圆角霓虹描边（青色 `#00e5ff` × 紫色 `#a855f7`）
- 深色渐变底 + 网格纹理 + 径向辉光
- 自定义状态指示灯（就绪 / 检测中 / 成功 / 失败，带呼吸动画）
- 主按钮悬停高度动画，卡片式模型行
- 全局 QSS 主题，含 hover / pressed / disabled 全态

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 打包

```bash
pip install pyinstaller
pyinstaller build.spec --noconfirm
# 产物: dist/一键测模型.exe
```

## 使用

1. 填入 **BASE URL**（例如 `http://localhost:8082/v1`，或任意中转站地址）
2. 填入 **API Key**（检测模型列表可留空，**测试模型响应时间必须填写**）
3. 点「⚡ 一键检测」拉取模型列表
4. 点单行「测试」按钮，或「⚡ 全部测试」批量跑延迟
5. 「导出 ▾」保存结果

## 接口约定

只依赖两个标准 OpenAI 兼容端点：

```
GET  {BASE URL}/models              -> {"data": [{"id": "...", "owned_by": "..."}]}
POST {BASE URL}/chat/completions    -> {"choices": [...]}
```

测试请求体：

```json
{
  "model": "<model id>",
  "messages": [{"role": "user", "content": "hi"}],
  "max_tokens": 1,
  "stream": false
}
```

## 错误处理

工具对以下情况给出明确中文提示，而不是静默失败：

- `ConnectTimeout` → 连接超时
- `ReadTimeout` → 读取超时
- `ConnectionError` → 连接失败
- `RequestException` → 请求异常
- 非 200 → 附带 HTTP 状态码与响应体片段
- 非法 JSON → 解析失败
- 缺少 `data` 字段 → 格式异常
- `401/403` → API Key 无效或无权限
- `404` → 模型不存在或未部署
- `429` → 额度不足或触发限流

## 配置存储

配置与历史记录通过 **`QSettings`** 存入 **Windows 注册表**（`HKCU\Software\YiJianCeAPI\一键测API`），不产生外部文件。

若检测到旧版 `config.json` / `history.json` 位于程序目录，会自动迁移进注册表并删除原文件。

## 项目结构

```
.
├── main.py                    # 全部源码（单文件，1372 行）
├── requirements.txt
├── build.spec                 # PyInstaller 打包配置
├── README.md
├── CHANGELOG.md               # 版本变更记录
├── LICENSE
└── docs_bytecode_disasm.txt   # 字节码反汇编存档（用于核对逻辑）
```

## 源码结构

```
main.py
├── 常量层        APP_NAME / APP_VERSION / 主题色 / MAX_CONCURRENT_TESTS
├── 存储层        app_dir / _st / load_config / save_config_data
│                 load_history / save_history / _migrate_legacy_files
├── 数据层        family_of / normalize_models
├── 渲染          make_app_pixmap / GLOBAL_QSS
├── 线程          ApiWorker         → GET /models
│                 ModelTestWorker   → POST /chat/completions
├── UI 组件       StatusDot / DetectButton / ModelRow
│                 RootWidget / WindowFrame / TitleBar
│                 HistoryRow / HistoryDialog
└── 主窗口        MainWindow（检测、批量测试队列、导出、历史、toast）
```

## License

MIT
