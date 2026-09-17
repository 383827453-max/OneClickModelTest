"""v1.2.3 冒烟测试：配置一键导入 / 导出 JSON。

不联网、不写注册表（save_config_data / load_config 被替换为内存实现）。
"""
import json
import os
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _watchdog(seconds=60):
    """防止对话框/菜单意外阻塞把 CI 挂死。"""
    time.sleep(seconds)
    print("\nFAIL  测试超时 %ds，疑似被模态对话框阻塞" % seconds)
    os._exit(2)


threading.Thread(target=_watchdog, daemon=True).start()

import main  # noqa: E402

# 阻断注册表读写
_STORE = {}
main.save_config_data = lambda data: (_STORE.update(data), True)[1]
main.load_config = lambda: dict(main.DEFAULT_CONFIG)

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

app = QApplication([])

checks = []


def ck(name, cond, extra=""):
    checks.append((name, bool(cond), extra))


# ---------- 1. 导出 payload 结构 ----------
w = main.MainWindow()
w.ed_url.setText("http://127.0.0.1:8082/v1")
w.ed_key.setText("sk-export-test")
w.sp_timeout.setValue(21)
w.sp_conf.setValue(5)
w.sp_maxtok.setValue(128)
w.logpanel.ed_alias.setText("金贝贝")

p = w._config_payload()
ck("payload 是 dict", isinstance(p, dict))
ck("带 app 标识", p.get("app") == main.APP_NAME)
ck("带 kind=config", p.get("kind") == "config")
ck("带 version", p.get("version") == main.APP_VERSION)
ck("带 exported_at", bool(p.get("exported_at")))
ck("含安全提示 note", "API Key" in p.get("note", ""))
cfg = p.get("config", {})
ck("config 是 dict", isinstance(cfg, dict))
ck("config 覆盖全部默认键", set(cfg) == set(main.DEFAULT_CONFIG),
   "缺: %s" % (set(main.DEFAULT_CONFIG) - set(cfg)))
ck("导出值取自界面 base_url", cfg.get("base_url") == "http://127.0.0.1:8082/v1")
ck("导出值取自界面 api_key", cfg.get("api_key") == "sk-export-test")
ck("导出值取自界面 timeout", cfg.get("timeout") == 21)
ck("导出值取自界面 并发", cfg.get("test_concurrency") == 5)
ck("导出值取自界面 max_tokens", cfg.get("max_tokens") == 128)
ck("导出值取自界面 别名", cfg.get("account_alias") == "金贝贝")

# ---------- 2. 端到端：写文件 → 清空 → 读文件 ----------
tmp = tempfile.mkdtemp(prefix="ocmt_cfg_")
path = os.path.join(tmp, "cfg.json")
orig_save = QFileDialog.getSaveFileName
orig_open = QFileDialog.getOpenFileName
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, "JSON 文件 (*.json)"))
w.export_config_json()
ck("导出后文件已生成", os.path.exists(path))
raw = json.load(open(path, encoding="utf-8"))
ck("落盘 JSON 可解析", isinstance(raw, dict))
ck("落盘含 config 段", isinstance(raw.get("config"), dict))
ck("落盘未含未知键", set(raw.get("config", {})) <= set(main.DEFAULT_CONFIG))

# 清空界面，再从文件导入
w.ed_url.setText("")
w.ed_key.setText("")
w.sp_timeout.setValue(1)
w.sp_conf.setValue(1)
w.sp_maxtok.setValue(1)
w.logpanel.ed_alias.setText("")
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, "JSON 文件 (*.json)"))
w.import_config_json()
ck("导入后回填 base_url", w.ed_url.text() == "http://127.0.0.1:8082/v1")
ck("导入后回填 api_key", w.ed_key.text() == "sk-export-test")
ck("导入后回填 timeout", w.sp_timeout.value() == 21)
ck("导入后回填 并发", w.sp_conf.value() == 5)
ck("导入后回填 max_tokens", w.sp_maxtok.value() == 128)
ck("导入后回填 别名", w.logpanel.ed_alias.text() == "金贝贝")
ck("导入后写入存储", _STORE.get("base_url") == "http://127.0.0.1:8082/v1")

# ---------- 3. 裸配置（无 config 包装）也能导入 ----------
w.ed_url.setText("")
w._apply_imported({"base_url": "http://bare.local/v1", "timeout": 9}, "裸配置")
ck("裸配置可导入", w.ed_url.text() == "http://bare.local/v1")
ck("裸配置回填数值", w.sp_timeout.value() == 9)

# ---------- 4. 非法输入被拒绝 / 字段被过滤 ----------
got = main.MainWindow._parse_config_payload(
    {"config": {"timeout": "abc", "test_concurrency": None,
                "base_url": 123, "unknown_key": "x",
                "api_key": "sk-ok", "max_tokens": "77"}})
ck("非数字 timeout 被丢弃", "timeout" not in got)
ck("None 数值被丢弃", "test_concurrency" not in got)
ck("非字符串 base_url 被丢弃", "base_url" not in got)
ck("未知键被忽略", "unknown_key" not in got)
ck("合法 api_key 保留", got.get("api_key") == "sk-ok")
ck("数字字符串 max_tokens 转 int", got.get("max_tokens") == 77)

ck("非 dict 输入返回空", main.MainWindow._parse_config_payload("nope") == {})
ck("list 输入返回空", main.MainWindow._parse_config_payload([1, 2]) == {})

# 空 base_url 应被拒
before = w.ed_url.text()
w._apply_imported({"config": {"base_url": "", "timeout": 33}}, "空地址")
ck("空 base_url 被拒绝", w.ed_url.text() == before)
ck("空 base_url 不写入 timeout", w.sp_timeout.value() != 33)

# 无有效字段应被拒
w._apply_imported({"foo": "bar"}, "垃圾")
ck("无有效字段不崩", True)

# ---------- 5. 布尔字段 ----------
got2 = main.MainWindow._parse_config_payload(
    {"always_on_top": True, "show_log": "false"})
ck("bool True 保留", got2.get("always_on_top") is True)
ck("字符串 'false' 转 False", got2.get("show_log") is False)

# ---------- 6. 剪贴板 ----------
w.ed_url.setText("http://clip.local/v1")
w.ed_key.setText("sk-clip")
w.copy_config_json()
clip = QApplication.clipboard().text()
ck("剪贴板拿到 JSON", clip.strip().startswith("{"))
parsed = json.loads(clip)
ck("剪贴板 JSON 可解析", parsed.get("kind") == "config")

w.ed_url.setText("")
w.paste_config_json()
ck("从剪贴板导入回填", w.ed_url.text() == "http://clip.local/v1")

QApplication.clipboard().setText("not json at all")
w.ed_url.setText("http://keep.local/v1")
w.paste_config_json()
ck("剪贴板非 JSON 时不覆盖", w.ed_url.text() == "http://keep.local/v1")

# ---------- 7. 恢复默认 ----------
w.reset_config()
ck("reset 后回到默认 base_url",
   w.ed_url.text() == main.DEFAULT_CONFIG["base_url"])
ck("reset 后回到默认 max_tokens",
   w.sp_maxtok.value() == main.DEFAULT_CONFIG["max_tokens"])
ck("reset 后回到默认别名", w.logpanel.ed_alias.text() == "")

# ---------- 8. 控件与菜单接线 ----------
ck("配置按钮存在", hasattr(w, "btn_cfg"))
ck("配置按钮文本", w.btn_cfg.text() == "配置 ▾")
ck("导入导出方法齐全",
   all(hasattr(w, n) for n in ("export_config_json", "import_config_json",
                               "copy_config_json", "paste_config_json",
                               "reset_config", "show_config_menu")))

# 真点一次按钮验证接线。QMenu.exec 是 C++ 绑定，Python 层覆盖不掉（会真弹菜单挂住），
# 所以在建窗口之前把类方法换成探针 —— 这样 connect 时绑定到的就是探针。
_opened = []
_real_menu = main.MainWindow.show_config_menu
main.MainWindow.show_config_menu = lambda self: _opened.append(1)
try:
    w_probe = main.MainWindow()
    w_probe.btn_cfg.click()
finally:
    main.MainWindow.show_config_menu = _real_menu
ck("点击配置按钮触发菜单处理", len(_opened) == 1, "opened=%d" % len(_opened))
ck("探针窗口已释放", True)

QFileDialog.getSaveFileName = orig_save
QFileDialog.getOpenFileName = orig_open

# ---------- 汇总 ----------
bad = [c for c in checks if not c[1]]
for name, ok, extra in checks:
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name,
                          ("   <- " + extra) if (extra and not ok) else ""))
print("\n%d/%d passed" % (len(checks) - len(bad), len(checks)))
sys.exit(1 if bad else 0)
