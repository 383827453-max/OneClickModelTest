"""v1.2.5 冒烟测试：sub2api 账号格式的导入 / 导出。

不联网、不写注册表。
"""
import copy
import json
import os
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _watchdog(seconds=60):
    time.sleep(seconds)
    print("\nFAIL  测试超时 %ds" % seconds)
    os._exit(2)


threading.Thread(target=_watchdog, daemon=True).start()

import main  # noqa: E402

_STORE = {}
main.save_config_data = lambda d: (_STORE.update(d), True)[1]
main.load_config = lambda: dict(main.DEFAULT_CONFIG)

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

app = QApplication([])
checks = []


def ck(name, cond, extra=""):
    checks.append((name, bool(cond), extra))


# 用户提供的真实 sub2api 样本
REAL = (r"E:\AI\DSH\home\attachments\v1\files\f7"
        r"\f77e8d237d6e7d5f226b84cea464c23dcdc00a3f3ed474af6abff83d41ca4086"
        r"\sub2api-account-20260918015818.json")

w = main.MainWindow()
w.ed_url.setText("https://www.a6api.cc.cd/v1")
w.ed_key.setText("sk-e09262139bd5a8c403e9536912481b84e85c5008443f4167f72d1be3ccaa235f")
w.logpanel.ed_alias.setText("福利生图")
w.sp_conf.setValue(10)

# ---------- 1. 导出结构必须是 sub2api 格式 ----------
p = w._sub2api_payload()
ck("顶层是 dict", isinstance(p, dict))
ck("含 exported_at", isinstance(p.get("exported_at"), str))
ck("exported_at 是 ISO8601 UTC", p.get("exported_at", "").endswith("Z")
   and "T" in p.get("exported_at", ""), repr(p.get("exported_at")))
ck("含 proxies 空数组", p.get("proxies") == [])
ck("含 accounts 数组", isinstance(p.get("accounts"), list) and len(p["accounts"]) == 1)
ck("不再有旧的 app/kind/config 顶层键",
   not any(k in p for k in ("app", "kind", "config")),
   "多了: %s" % [k for k in ("app", "kind", "config") if k in p])

a = p["accounts"][0]
ck("account.name = 别名", a.get("name") == "福利生图", repr(a.get("name")))
ck("account.platform = openai", a.get("platform") == "openai")
ck("account.type = apikey", a.get("type") == "apikey")
ck("account 含 credentials", isinstance(a.get("credentials"), dict))
ck("credentials.base_url", a["credentials"].get("base_url") == "https://www.a6api.cc.cd/v1",
   repr(a["credentials"].get("base_url")))
ck("credentials.api_key", a["credentials"].get("api_key", "").startswith("sk-e09262"),
   repr(a["credentials"].get("api_key"))[:24])
ck("account.concurrency = 并发数", a.get("concurrency") == 10, repr(a.get("concurrency")))
ck("account.priority = 1", a.get("priority") == 1)
ck("account.rate_multiplier = 1", a.get("rate_multiplier") == 1)
ck("account.auto_pause_on_expired = true", a.get("auto_pause_on_expired") is True)
ck("account 含 extra", isinstance(a.get("extra"), dict))

# 键集应与真实样本一致
if os.path.exists(REAL):
    real = json.load(open(REAL, encoding="utf-8"))
    ra = real["accounts"][0]
    ck("账号键集与真实样本一致",
       set(a.keys()) == set(ra.keys()),
       "我方多: %s / 少: %s" % (set(a) - set(ra), set(ra) - set(a)))
    ck("顶层键集与真实样本一致",
       set(p.keys()) == set(real.keys()),
       "我方多: %s / 少: %s" % (set(p) - set(real), set(real) - set(p)))
    ck("credentials 键集是真实样本子集",
       set(a["credentials"]) <= set(ra["credentials"]),
       "多了: %s" % (set(a["credentials"]) - set(ra["credentials"])))

# ---------- 2. 导入用户真实文件 ----------
print("--- 用户真实文件:", "存在" if os.path.exists(REAL) else "缺失", "---")
if os.path.exists(REAL):
    real = json.load(open(REAL, encoding="utf-8"))
    w.ed_url.setText("")
    w.ed_key.setText("")
    w.logpanel.ed_alias.setText("")
    w._apply_imported(copy.deepcopy(real), "真实样本")

    ck("导入后 base_url = 样本里的值",
       w.ed_url.text() == "https://api.apisaver.com", repr(w.ed_url.text()))
    ck("导入后 api_key = 样本里的值",
       w.ed_key.text() == "sk-5zQpQMkRyYg60WPJcl8d3MRVsoOuyURKmkDDm5IbO1Y4jdI6",
       repr(w.ed_key.text())[:28])
    ck("导入后 账号名 = 福利生图",
       w.logpanel.ed_alias.text() == "福利生图", repr(w.logpanel.ed_alias.text()))
    ck("导入后 并发数 = 10", w.sp_conf.value() == 10, str(w.sp_conf.value()))
    ck("导入后已写入存储", _STORE.get("base_url") == "https://api.apisaver.com")
    ck("导入后状态条账号名正确", w._account_name() == "福利生图")

# ---------- 3. 文件往返（导出 → 重新导入） ----------
w.ed_url.setText("https://round.trip/v1")
w.ed_key.setText("sk-roundtrip-key")
w.logpanel.ed_alias.setText("往返账号")
w.sp_conf.setValue(7)

tmp = tempfile.mkdtemp(prefix="ocmt_sub2_")
path = os.path.join(tmp, "sub2api-account-test.json")
_rs, _ro = QFileDialog.getSaveFileName, QFileDialog.getOpenFileName
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, "JSON"))
w.export_config_json()
ck("导出文件已生成", os.path.exists(path))
raw = json.load(open(path, encoding="utf-8"))
ck("落盘文件是 sub2api 结构", "accounts" in raw and "proxies" in raw)
ck("落盘文件名带 sub2api-account 前缀",
   os.path.basename(path).startswith("sub2api-account-"))

w.ed_url.setText("")
w.ed_key.setText("")
w.logpanel.ed_alias.setText("")
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, "JSON"))
w.import_config_json()
ck("往返后 base_url 一致", w.ed_url.text() == "https://round.trip/v1", w.ed_url.text())
ck("往返后 api_key 一致", w.ed_key.text() == "sk-roundtrip-key")
ck("往返后 别名一致", w.logpanel.ed_alias.text() == "往返账号")
ck("往返后 并发一致", w.sp_conf.value() == 7)

# ---------- 4. 多账号文件 ----------
multi = {
    "exported_at": "2026-09-18T00:00:00Z",
    "proxies": [],
    "accounts": [
        {"name": "甲", "platform": "openai", "type": "apikey",
         "credentials": {"api_key": "sk-a", "base_url": "https://a.example/v1"},
         "concurrency": 5},
        {"name": "乙", "platform": "openai", "type": "apikey",
         "credentials": {"api_key": "sk-b", "base_url": "https://b.example/v1"},
         "concurrency": 9},
    ],
}
cfg, metas = main.MainWindow._parse_sub2api_payload(multi)
ck("多账号识别出 2 条", len(metas) == 2, str(len(metas)))
ck("多账号取第 1 个 name", cfg.get("account_alias") == "甲")
ck("多账号取第 1 个 base_url", cfg.get("base_url") == "https://a.example/v1")
ck("多账号取第 1 个 concurrency", cfg.get("test_concurrency") == 5)
w.logpanel.clear_log()
w._apply_imported(copy.deepcopy(multi), "多账号")
txt = w.logpanel.view.toPlainText()
ck("多账号导入后提示 N 个账号", "2 个账号" in txt, repr(txt[:80]))
ck("多账号导入后列出每个账号", ("甲" in txt and "乙" in txt))

# ---------- 5. 容错 ----------
cfg2, m2 = main.MainWindow._parse_sub2api_payload({"accounts": []})
ck("空 accounts 返回空", cfg2 == {} and m2 == [])
cfg3, m3 = main.MainWindow._parse_sub2api_payload({"accounts": "notalist"})
ck("accounts 非列表返回空", cfg3 == {})
cfg4, m4 = main.MainWindow._parse_sub2api_payload({"foo": 1})
ck("无 accounts 键返回空", cfg4 == {})
cfg5, m5 = main.MainWindow._parse_sub2api_payload(
    {"accounts": [{"name": "x", "credentials": {"api_key": "k"}}]})
ck("缺 base_url 时不生成 base_url", "base_url" not in cfg5)
ck("缺 base_url 但有 name 时仍产出 name", cfg5.get("account_alias") == "x")
cfg6, _ = main.MainWindow._parse_sub2api_payload(
    {"accounts": [{"name": "y", "credentials": {"base_url": "  https://pad.example/v1  "}}]})
ck("base_url 两端空白被裁剪", cfg6.get("base_url") == "https://pad.example/v1")
cfg7, _ = main.MainWindow._parse_sub2api_payload({"accounts": [None, 42, "s"]})
ck("非法账号元素被跳过", cfg7 == {})
cfg8, _ = main.MainWindow._parse_sub2api_payload(
    {"accounts": [{"name": "z", "concurrency": 9999,
                   "credentials": {"base_url": "https://c.example/v1"}}]})
ck("超大 concurrency 被夹到 32", cfg8.get("test_concurrency") == 32,
   str(cfg8.get("test_concurrency")))

# 空 base_url 的账号应被拒绝
before = w.ed_url.text()
w._apply_imported({"accounts": [{"name": "bad", "credentials": {"api_key": "k"}}]}, "坏账号")
ck("账号缺 base_url 时整体拒绝", w.ed_url.text() == before)

# ---------- 6. 旧格式仍可导入（向后兼容） ----------
w.ed_url.setText("")
w._apply_imported({"config": {"base_url": "https://legacy.example/v1",
                              "timeout": 12}}, "旧格式")
ck("旧格式仍可导入", w.ed_url.text() == "https://legacy.example/v1")
ck("旧格式字段生效", w.sp_timeout.value() == 12)

# ---------- 7. 剪贴板 ----------
w.ed_url.setText("https://clip.example/v1")
w.logpanel.ed_alias.setText("剪贴账号")
w.copy_config_json()
clip = json.loads(QApplication.clipboard().text())
ck("剪贴板是 sub2api 结构", "accounts" in clip and "proxies" in clip)
ck("剪贴板账号名正确", clip["accounts"][0]["name"] == "剪贴账号")

QFileDialog.getSaveFileName = _rs
QFileDialog.getOpenFileName = _ro

bad = [c for c in checks if not c[1]]
for name, ok, extra in checks:
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name,
                          ("   <- " + extra) if (extra and not ok) else ""))
print("\n%d/%d passed" % (len(checks) - len(bad), len(checks)))
sys.exit(1 if bad else 0)
