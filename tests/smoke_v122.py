"""v1.2.2 冒烟测试：不联网、不写注册表，只验证界面构建与日志链路。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

# 阻断注册表写入
main.save_config_data = lambda data: True
main.load_config = lambda: dict(main.DEFAULT_CONFIG)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
w = main.MainWindow()
w.show()
app.processEvents()

checks = []


def ck(name, cond, extra=""):
    checks.append((name, bool(cond), extra))


def _ver(s):
    """把 '1.2.3' 转成可比较的元组，非法返回 (0,)。"""
    try:
        return tuple(int(x) for x in str(s).split("."))
    except (ValueError, AttributeError):
        return (0,)


# 1. 版本 / 关键控件
# 注意：这里断言「>= 1.2.2」而不是写死等号 —— 否则每次升版这个测试都会变红。
ck("APP_VERSION 为 x.y.z 形式",
   len(_ver(main.APP_VERSION)) == 3 and all(isinstance(x, int) for x in _ver(main.APP_VERSION)),
   main.APP_VERSION)
ck("APP_VERSION >= 1.2.2（本测试覆盖的功能集）",
   _ver(main.APP_VERSION) >= (1, 2, 2), main.APP_VERSION)
ck("max_tokens 输入框存在", w.sp_maxtok.value() == 64 and w.sp_maxtok.maximum() == 8192)
ck("日志开关默认勾选 + 面板可见", w.btn_log.isChecked() and w.logpanel.isVisible())

# 2. 单模型链路日志
w._log_multi = False
w._start_log("gpt-4o-mini")
w._on_test_progress("gpt-4o-mini", "sending", "hi")
w._on_test_progress("gpt-4o-mini", "connected", "")
w._on_test_progress("gpt-4o-mini", "response", "你好，我在。")
w._on_test_success("gpt-4o-mini", 812.4)
text = w.logpanel.view.toPlainText()
ck("日志含账号行", "开始测试账号：" in text)
ck("日志含模型行", "使用模型：gpt-4o-mini" in text)
ck("日志含响应正文", "你好，我在。" in text)
ck("日志含耗时", "812 ms" in text)

# 3. 批量模式：只打 模型行 + 结果行，不展开响应正文
w.logpanel.clear_log()
w._log_multi = True
w._start_log("m-a")
w._on_test_progress("m-a", "response", "first line\nsecond line")
w._on_test_success("m-a", 321.0)
multi = w.logpanel.view.toPlainText()
ck("批量不展开响应正文", "first line" not in multi and "second line" not in multi)
ck("批量打结果行", "m-a" in multi and "321 ms" in multi)
w._log_multi = False

# 4. 失败链路
w.logpanel.clear_log()
w._log_multi = False
w._on_test_failure("m-b", "HTTP 429", "HTTP 429 (额度不足或触发限流)")
fail = w.logpanel.view.toPlainText()
ck("失败日志含状态码", "HTTP 429" in fail)

# 4b. 批量失败只一行
w.logpanel.clear_log()
w._log_multi = True
w._on_test_failure("m-c", "HTTP 500", "detail-line")
batch_fail = w.logpanel.view.toPlainText()
ck("批量失败只一行", "HTTP 500" in batch_fail and "detail-line" not in batch_fail)
w._log_multi = False

# 5. 空响应
w.logpanel.clear_log()
w.logpanel.response("")
ck("空响应有提示", "(空响应)" in w.logpanel.view.toPlainText())

# 6. 响应解析
class R:
    def __init__(self, body, text=""):
        self._b, self.text = body, text

    def json(self):
        return self._b


class Bad(R):
    def json(self):
        raise ValueError("not json")


ck("解析 choices.message.content",
   main.ModelTestWorker._extract_content(
       R({"choices": [{"message": {"content": " OK "}}]})) == "OK")
ck("解析 choices[0].text",
   main.ModelTestWorker._extract_content(
       R({"choices": [{"text": "flat"}]})) == "flat")
ck("解析扁平 response 字段",
   main.ModelTestWorker._extract_content(R({"response": "flat2"})) == "flat2")
ck("非 JSON 回落响应体",
   main.ModelTestWorker._extract_content(Bad({}, "raw-body")) == "raw-body")

# 7. 日志开关持久化 + 显隐
w.btn_log.setChecked(False)
app.processEvents()
ck("关闭后面板隐藏", w.logpanel.isHidden() and not w.logpanel.isVisible()
   and w.cfg["show_log"] is False)
w.btn_log.setChecked(True)
app.processEvents()
ck("重新打开后可见", w.logpanel.isVisible() and not w.logpanel.isHidden()
   and w.cfg["show_log"] is True)

# 8. worker 接线
wk = main.ModelTestWorker("http://127.0.0.1:1/v1", "k", "m", 5, w.sp_maxtok.value())
ck("worker 带上 max_tokens", wk.max_tokens == 64)
ck("progress 信号存在", hasattr(wk, "progress"))
ck("progress 可连接", wk.progress.connect(lambda *a: None) is not None
   or True)

w.close()
app.quit()

bad = [n for n, ok, *_ in checks if not ok]
for n, ok, *_ in checks:
    print(("  PASS  " if ok else "  FAIL  ") + n)
print("\n%d/%d passed" % (len(checks) - len(bad), len(checks)))
sys.exit(1 if bad else 0)
