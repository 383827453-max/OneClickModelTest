"""一键测API - 科技风 API 模型检测工具
功能：一键检测 OpenAI 兼容接口 (GET {base_url}/models) 的可用模型
      支持单个/批量测试模型响应时间 (POST {base_url}/chat/completions)"""

import csv
import json
import os
import sys
import time
from datetime import datetime

import requests
from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, QSettings, QSize,
                              Qt, QThread, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QKeySequence,
                            QLinearGradient, QPainter, QPainterPath, QPen,
                            QPixmap, QPolygonF, QRadialGradient, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                               QFileDialog, QFrame, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QPushButton, QSizeGrip,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

APP_NAME = '一键测API'
APP_VERSION = '1.2.3'
C_CYAN = '#00e5ff'
C_PURPLE = '#a855f7'
C_GREEN = '#00ff9d'
C_RED = '#ff3b6b'
C_YELLOW = '#ffd166'
C_TEXT = '#d9e6ff'
C_TEXT_DIM = '#7286a8'
MAX_CONCURRENT_TESTS = 3


def app_dir():
    """Return the directory the executable/script lives in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _st():
    """QSettings store: config + history live in the registry, no external files."""
    return QSettings("YiJianCeAPI", APP_NAME)


CONFIG_PATH = os.path.join(app_dir(), "config.json")
HISTORY_PATH = os.path.join(app_dir(), "history.json")

DEFAULT_CONFIG = {
    "base_url": "http://localhost:8082/v1",
    "api_key": "",
    "timeout": 15,
    "test_timeout": 30,
    "test_concurrency": 3,
    "always_on_top": False,
    "account_alias": "",
    "max_tokens": 64,
    "show_log": True,
}


def _migrate_legacy_files():
    """Migrate a legacy config.json / history.json sitting next to the exe into
    the registry store, then delete the files."""
    st = _st()
    for path, key in ((CONFIG_PATH, "config"), (HISTORY_PATH, "history")):
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.setValue(key, json.dumps(data, ensure_ascii=False))
            f.close()
            os.remove(path)
        except Exception:
            pass


def load_config():
    """Load config from the registry store, falling back to defaults."""
    st = _st()
    raw = st.value("config", "")
    cfg = dict(DEFAULT_CONFIG)
    if raw:
        try:
            got = json.loads(raw)
            if isinstance(got, dict):
                cfg.update(got)
        except Exception:
            pass
    return cfg


def save_config_data(cfg):
    """Persist the config dict into the registry store."""
    try:
        _st().setValue("config", json.dumps(cfg, ensure_ascii=False))
        return True
    except OSError:
        return False


def load_history():
    """Load the detection history list."""
    raw = _st().value("history", "")
    if not raw:
        return []
    try:
        got = json.loads(raw)
        return got if isinstance(got, list) else []
    except Exception:
        return []


def save_history(items):
    """Persist the detection history list."""
    try:
        _st().setValue("history", json.dumps(items, ensure_ascii=False))
        return True
    except OSError:
        return False


def family_of(model_id):
    """Guess the model family/vendor tag from a model id."""
    mid = (model_id or "").lower()
    table = (
        ("gpt", "OpenAI"),
        ("o1", "OpenAI"),
        ("o3", "OpenAI"),
        ("claude", "Anthropic"),
        ("gemini", "Google"),
        ("deepseek", "DeepSeek"),
        ("qwen", "Qwen"),
        ("glm", "Zhipu"),
        ("llama", "Meta"),
        ("mistral", "Mistral"),
        ("kimi", "Moonshot"),
        ("grok", "xAI"),
    )
    for key, name in table:
        if key in mid:
            return name
    return "unknown"


def normalize_models(data):
    """Normalize an OpenAI-compatible /models payload into a model id list."""
    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id")
            if isinstance(mid, str) and mid:
                out.append({"id": mid, "owned_by": it.get("owned_by", "")})
        elif isinstance(it, str) and it:
            out.append({"id": it, "owned_by": ""})
    return out



def make_app_pixmap(size=256):
    """Draw the app icon at runtime: neon rounded square + bolt."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    margin = size * 0.06
    rect = QRectF(margin, margin, size - margin * 2, size - margin * 2)
    p.setBrush(QColor(9, 13, 30))
    p.setPen(QPen(QColor(C_CYAN), max(1.5, size * 0.012)))
    p.drawRoundedRect(rect, size * 0.2, size * 0.2)

    bolt = QPolygonF([
        QPointF(size * 0.56, size * 0.18),
        QPointF(size * 0.34, size * 0.54),
        QPointF(size * 0.48, size * 0.54),
        QPointF(size * 0.44, size * 0.82),
        QPointF(size * 0.66, size * 0.46),
        QPointF(size * 0.52, size * 0.46),
    ])
    p.setBrush(QColor(C_CYAN))
    p.setPen(Qt.NoPen)
    p.drawPolygon(bolt)
    p.end()
    return pm


class ApiWorker(QThread):
    """Background thread: request {base_url}/models"""

    succeeded = Signal(list, float)
    failed = Signal(str, str)

    def __init__(self, base_url, api_key, timeout=15):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def run(self):
        base = (self.base_url or "").strip().rstrip("/")
        url = base + "/models"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        session = requests.Session()
        session.trust_env = False
        t0 = time.perf_counter()
        try:
            resp = session.get(url, headers=headers, timeout=self.timeout)
        except requests.exceptions.ConnectTimeout:
            self.failed.emit(
                "连接超时",
                "超过 " + str(self.timeout) + " 秒无法建立连接。\n目标: " + url
                + "\n\n请确认服务已启动、地址与端口正确。")
            return
        except requests.exceptions.ReadTimeout:
            self.failed.emit(
                "读取超时",
                "超过 " + str(self.timeout) + " 秒未收到完整响应。\n目标: " + url)
            return
        except requests.exceptions.ConnectionError:
            self.failed.emit(
                "连接失败",
                "无法连接到目标地址。\n目标: " + url
                + "\n\n请确认服务已启动、地址与端口正确。")
            return
        except requests.exceptions.RequestException as e:
            self.failed.emit("请求异常", str(e) + "\n\n" + url)
            return

        elapsed = (time.perf_counter() - t0) * 1000.0

        if resp.status_code != 200:
            self.failed.emit(
                "HTTP " + str(resp.status_code),
                "接口返回了错误状态码。\nURL: " + url
                + "\n\n响应内容:\n" + (resp.text or "")[:800])
            return

        try:
            data = resp.json()
        except ValueError:
            self.failed.emit(
                "解析失败",
                "响应不是有效的 JSON:\n\n" + (resp.text or "")[:500])
            return

        models = normalize_models(data)
        if not models:
            self.failed.emit(
                "格式异常",
                "返回 JSON 中未找到模型列表字段 data。\n\n"
                + json.dumps(data, ensure_ascii=False)[:500])
            return

        self.succeeded.emit(models, elapsed)


class ModelTestWorker(QThread):
    """Background thread: test single-model latency (POST /chat/completions)"""

    succeeded = Signal(str, float)
    failed = Signal(str, str, str)
    # (model_id, event, payload) — event ∈ {sending, connected, response}
    progress = Signal(str, str, str)

    def __init__(self, base_url, api_key, model_id, timeout=30, max_tokens=64):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model_id = model_id
        self.timeout = timeout
        self.max_tokens = max(1, int(max_tokens))

    @staticmethod
    def _extract_content(resp):
        """Best-effort pull of the assistant text out of an OpenAI-style reply."""
        try:
            body = resp.json()
        except ValueError:
            return (resp.text or "").strip()[:2000]

        if isinstance(body, dict):
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    msg = first.get("message")
                    if isinstance(msg, dict):
                        c = msg.get("content")
                        if isinstance(c, str) and c.strip():
                            return c.strip()
                    t = first.get("text")
                    if isinstance(t, str) and t.strip():
                        return t.strip()
            # non-standard gateways: try the common flat fields
            for key in ("content", "response", "output_text", "message"):
                v = body.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return ""

    def run(self):
        base = (self.base_url or "").strip().rstrip("/")
        url = base + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (self.api_key or ""),
        }
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        session = requests.Session()
        session.trust_env = False
        self.progress.emit(self.model_id, "sending", "hi")
        t0 = time.perf_counter()
        try:
            resp = session.post(url, headers=headers, json=payload,
                                timeout=self.timeout)
        except requests.exceptions.ConnectTimeout:
            self.failed.emit(self.model_id, "连接超时",
                             "连接超时: 超过 %s 秒无法建立连接" % self.timeout)
            return
        except requests.exceptions.ReadTimeout:
            self.failed.emit(self.model_id, "响应超时",
                             "响应超时: 超过 %s 秒未收到回复" % self.timeout)
            return
        except requests.exceptions.ConnectionError:
            self.failed.emit(self.model_id, "连接失败", "连接失败: 无法连接到服务")
            return
        except requests.exceptions.RequestException as e:
            self.failed.emit(self.model_id, "请求异常", "请求异常: %s" % e)
            return

        elapsed = (time.perf_counter() - t0) * 1000.0
        self.progress.emit(self.model_id, "connected", "")

        if resp.status_code == 200:
            self.progress.emit(self.model_id, "response",
                               self._extract_content(resp))
            self.succeeded.emit(self.model_id, elapsed)
            return

        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    detail = str(err.get("message") or "")
                elif err:
                    detail = str(err)
        except ValueError:
            detail = (resp.text or "")[:120]

        tag = ""
        if resp.status_code in (401, 403):
            tag = " (API Key 无效或无权限)"
        elif resp.status_code == 404:
            tag = " (模型不存在或未部署)"
        elif resp.status_code == 429:
            tag = " (额度不足或触发限流)"

        self.progress.emit(self.model_id, "response", detail)
        self.failed.emit(self.model_id, "HTTP %s" % resp.status_code,
                         ("HTTP %s" % resp.status_code) + tag
                         + (": " + detail if detail else ""))


GLOBAL_QSS = """
* { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }
QWidget { color: #d9e6ff; }
QMainWindow, QDialog { background: transparent; }

QFrame#glass {
    background-color: rgba(13, 20, 42, 165);
    border: 1px solid rgba(0, 229, 255, 55);
    border-radius: 14px;
}
QFrame#errorBanner {
    background-color: rgba(64, 12, 28, 210);
    border: 1px solid rgba(255, 59, 107, 130);
    border-radius: 12px;
}

QLabel { background: transparent; }
QLabel#h1 { color: #00e5ff; font-size: 17px; font-weight: bold; }
QLabel#sub { color: #7286a8; font-size: 9px; }
QLabel#caption { color: #7286a8; font-size: 10px; font-weight: bold; }
QLabel#statName { color: #7286a8; font-size: 11px; }
QLabel#statValue { color: #8be9ff; font-size: 13px; font-weight: bold; font-family: "Consolas", "Cascadia Mono", monospace; }
QLabel#errorTitle { color: #ff7d9c; font-size: 12px; font-weight: bold; }
QLabel#errorDetail { color: #d9a3b0; font-size: 11px; font-family: "Consolas", "Cascadia Mono", monospace; }
QLabel#groupHeader { color: #00e5ff; font-size: 11px; font-weight: bold; padding-left: 12px; }
QLabel#footer { color: #4c5b78; font-size: 10px; }

QLineEdit, QSpinBox {
    background-color: rgba(5, 9, 22, 215);
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: 8px;
    padding: 8px 12px;
    color: #d9e6ff;
    selection-background-color: rgba(0, 229, 255, 90);
    selection-color: #04101f;
}
QLineEdit:focus, QSpinBox:focus { border: 1px solid #00e5ff; }
QSpinBox { padding-right: 22px; }

QPushButton#detectBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c6e0, stop:1 #8b3df0);
    color: #06121f;
    font-size: 17px;
    font-weight: bold;
    border: none;
    border-radius: 14px;
    padding: 14px 20px;
}
QPushButton#detectBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3fe3ff, stop:1 #ab66ff);
}
QPushButton#detectBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00a7c4, stop:1 #7430cc);
}
QPushButton#detectBtn:disabled {
    background: rgba(58, 72, 108, 130);
    color: rgba(217, 230, 255, 110);
}

QPushButton#ghostBtn, QToolButton#ghostBtn {
    background-color: rgba(0, 229, 255, 14);
    border: 1px solid rgba(0, 229, 255, 80);
    border-radius: 8px;
    color: #8be9ff;
    padding: 8px 16px;
    font-size: 12px;
}
QPushButton#ghostBtn:hover, QToolButton#ghostBtn:hover { background-color: rgba(0, 229, 255, 42); color: #d9f6ff; }
QPushButton#ghostBtn:pressed, QToolButton#ghostBtn:pressed { background-color: rgba(0, 229, 255, 70); }
QPushButton#ghostBtn:disabled { color: rgba(114, 134, 168, 120); border-color: rgba(114, 134, 168, 60); background-color: rgba(60, 70, 100, 20); }

QPushButton#dangerBtn {
    background-color: rgba(255, 59, 107, 16);
    border: 1px solid rgba(255, 59, 107, 110);
    border-radius: 8px;
    color: #ff8fa8;
    padding: 8px 16px;
    font-size: 12px;
}
QPushButton#dangerBtn:hover { background-color: rgba(255, 59, 107, 45); color: #ffd0da; }
QPushButton#dangerBtn:pressed { background-color: rgba(255, 59, 107, 75); }

QToolButton#titleBtn {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #7286a8;
    font-size: 13px;
    padding: 4px;
}
QToolButton#titleBtn:hover { background: rgba(0, 229, 255, 30); color: #d9e6ff; }
QToolButton#titleBtn:checked { color: #00e5ff; background: rgba(0, 229, 255, 25); }
QToolButton#closeBtn {
    background: transparent; border: none; border-radius: 8px;
    color: #7286a8; font-size: 14px; padding: 4px;
}
QToolButton#closeBtn:hover { background: rgba(255, 59, 107, 90); color: #ffffff; }

QPushButton#testBtn {
    background-color: rgba(168, 85, 247, 18);
    border: 1px solid rgba(168, 85, 247, 110);
    border-radius: 7px;
    color: #c99fff;
    padding: 3px 14px;
    font-size: 11px;
}
QPushButton#testBtn:hover { background-color: rgba(168, 85, 247, 45); color: #e8d4ff; }
QPushButton#testBtn:pressed { background-color: rgba(168, 85, 247, 75); }
QPushButton#testBtn:disabled { color: rgba(114, 134, 168, 110); border-color: rgba(114, 134, 168, 50); background-color: rgba(60, 70, 100, 15); }

QPushButton#copyBtn {
    background-color: rgba(0, 229, 255, 12);
    border: 1px solid rgba(0, 229, 255, 70);
    border-radius: 7px;
    color: #6fd8ef;
    padding: 3px 12px;
    font-size: 11px;
}
QPushButton#copyBtn:hover { background-color: rgba(0, 229, 255, 35); color: #d9f6ff; }
QPushButton#copyBtn:pressed { background-color: rgba(0, 229, 255, 60); }

QListWidget#modelList {
    background-color: rgba(7, 11, 26, 195);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 14px;
    padding: 6px;
    outline: none;
}
QListWidget#modelList::item { border-radius: 8px; }
QListWidget#modelList::item:hover { background: rgba(0, 229, 255, 14); }
QListWidget#modelList::item:selected { background: rgba(0, 229, 255, 28); }

QSplitter#mainSplit::handle { background: transparent; height: 8px; }
QSplitter#mainSplit::handle:hover { background: rgba(0, 229, 255, 40); }

QTextEdit#logView {
    background-color: rgba(3, 6, 16, 225);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 12px;
    padding: 8px 12px;
    color: #cfe3ff;
    font-family: "Consolas", "Cascadia Mono", "Courier New", monospace;
    font-size: 11px;
    selection-background-color: rgba(0, 229, 255, 90);
    selection-color: #04101f;
}
QTextEdit#logView QScrollBar:vertical {
    background: transparent; width: 8px; margin: 2px;
}
QTextEdit#logView QScrollBar::handle:vertical {
    background: rgba(0, 229, 255, 80); border-radius: 4px; min-height: 24px;
}
QTextEdit#logView QScrollBar::handle:vertical:hover { background: rgba(0, 229, 255, 140); }
QTextEdit#logView QScrollBar::add-line:vertical,
QTextEdit#logView QScrollBar::sub-line:vertical { height: 0; }
QTextEdit#logView QScrollBar::add-page:vertical,
QTextEdit#logView QScrollBar::sub-page:vertical { background: transparent; }

QLineEdit#logAlias {
    background-color: rgba(5, 9, 22, 200);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 7px;
    padding: 4px 10px;
    color: #8be9ff;
    font-size: 11px;
}
QLineEdit#logAlias:focus { border: 1px solid #00e5ff; }

QListWidget#historyList {
    background-color: rgba(7, 11, 26, 195);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 10px;
    padding: 4px;
    outline: none;
}
QListWidget#historyList::item { border-radius: 6px; }
QListWidget#historyList::item:hover { background: rgba(0, 229, 255, 14); }
QListWidget#historyList::item:selected { background: rgba(0, 229, 255, 28); }

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 8px 3px 8px 3px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 229, 255, 60); border-radius: 5px; min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: rgba(0, 229, 255, 110); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 0; }

QMenu {
    background-color: rgba(9, 14, 30, 248);
    border: 1px solid rgba(0, 229, 255, 90);
    border-radius: 10px;
    padding: 6px;
}
QMenu::item { color: #d9e6ff; padding: 8px 30px 8px 16px; border-radius: 6px; }
QMenu::item:selected { background: rgba(0, 229, 255, 45); }

QToolTip {
    background-color: #0a1226;
    color: #8be9ff;
    border: 1px solid rgba(0, 229, 255, 120);
    padding: 6px 9px;
}
"""


class StatusDot(QWidget):
    """Small animated status dot on the title bar."""

    def __init__(self, parent=None, size=10):
        super().__init__(parent)
        self._size = size
        self._color = QColor(C_TEXT_DIM)
        self._phase = 0
        self.setFixedSize(QSize(size, size))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(60)

    def set_status(self, level):
        if level == "ok":
            self._color = QColor(C_GREEN)
            self._timer.start()
        elif level == "busy":
            self._color = QColor(C_CYAN)
            self._timer.start()
        elif level == "error":
            self._color = QColor(C_RED)
            self._timer.stop()
        else:
            self._color = QColor(C_TEXT_DIM)
            self._timer.stop()
        self._phase = 0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 1) % 20
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        c = self._size / 2.0
        r = c - 1.5
        if self._timer.isActive():
            halo = QColor(self._color)
            halo.setAlpha(70 + int(60 * abs((self._phase / 10.0) - 1.0)))
            p.setBrush(QBrush(halo))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(c, c), r + 1.0, r + 1.0)
        p.setBrush(QBrush(self._color))
        p.setPen(QPen(self._color.lighter(140), 1))
        p.drawEllipse(QPointF(c, c), r, r)


class DetectButton(QPushButton):
    """Primary gradient action button with hover animation."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("detectBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(52)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, value):
        self.setMinimumHeight(int(value))

    def _animate_to(self, target):
        self._anim.stop()
        self._anim.setStartValue(self.minimumHeight())
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._animate_to(56)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(52)
        super().leaveEvent(event)


class ModelRow(QWidget):
    """One model row: index + model id + vendor tag + test result + test button."""

    def __init__(self, index, model, on_test=None, parent=None):
        super().__init__(parent)
        self.model_id = model.get("id", "")
        self.owned_by = model.get("owned_by", "") or family_of(self.model_id)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        self.idx = QLabel(str(index))
        self.idx.setObjectName("caption")
        self.idx.setFixedWidth(28)

        self.name = QLabel(self.model_id)
        self.name.setObjectName("statValue")
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.tag = QLabel(self.owned_by)
        self.tag.setObjectName("caption")

        self.result = QLabel("")
        self.result.setObjectName("caption")

        self.btn = QPushButton("测试")
        self.btn.setObjectName("testBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        if on_test is not None:
            self.btn.clicked.connect(lambda: on_test(self.model_id))

        lay.addWidget(self.idx)
        lay.addWidget(self.name, 1)
        lay.addWidget(self.tag)
        lay.addWidget(self.result)
        lay.addWidget(self.btn)

    def set_testing(self):
        self.btn.setEnabled(False)
        self.btn.setText("测中...")
        self.result.setText("测试中...")
        self.result.setStyleSheet("color: %s;" % C_YELLOW)

    def set_result(self, ms):
        self.btn.setEnabled(True)
        self.btn.setText("测试")
        self.result.setText("响应时间: %.0f ms" % ms)
        self.result.setStyleSheet("color: %s;" % C_GREEN)

    def set_error(self, tag):
        self.btn.setEnabled(True)
        self.btn.setText("重试")
        self.result.setText(str(tag))
        self.result.setStyleSheet("color: %s;" % C_RED)


class LogPanel(QWidget):
    """实时测试日志：逐步显示 账号 / 模型 / 请求 / 响应，确认模型是否真的回了话。"""

    C_KEY = "#7286a8"     # 标签
    C_VAL = "#8be9ff"     # 值
    C_RES = "#00ff9d"     # 响应正文 / 成功
    C_ERR = "#ff3b6b"     # 失败
    C_DIM = "#3a4a68"     # 分隔线
    C_WARN = "#ffd166"    # 提示

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self.setMinimumHeight(150)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("▍测试日志  TEST LOG")
        self.title.setObjectName("groupHeader")
        self.ed_alias = QLineEdit()
        self.ed_alias.setObjectName("logAlias")
        self.ed_alias.setPlaceholderText("账号别名（可选）")
        self.ed_alias.setFixedWidth(170)
        self.ed_alias.setToolTip("日志里「开始测试账号」显示的名字；留空则用 BASE URL 主机名")
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("ghostBtn")
        self.btn_clear.setFixedWidth(56)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_log)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.ed_alias)
        head.addWidget(self.btn_clear)
        lay.addLayout(head)

        self.view = QTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QTextEdit.WidgetWidth)
        self.view.document().setDefaultStyleSheet(
            "p{margin:0;padding:0;}"
            "span.k{color:%s;} span.v{color:%s;} span.r{color:%s;}"
            "span.e{color:%s;} span.d{color:%s;} span.w{color:%s;}"
            % (self.C_KEY, self.C_VAL, self.C_RES,
               self.C_ERR, self.C_DIM, self.C_WARN))
        lay.addWidget(self.view, 1)

    # ---------- 内部 ----------

    @staticmethod
    def _esc(s):
        return (str(s).replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))

    def _put(self, html):
        self.view.append(html)
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- 公开 API ----------

    def kv(self, key, value, cls="v"):
        """一行「标签：值」"""
        self._put('<p><span class="k">%s</span><span class="%s">%s</span></p>'
                  % (self._esc(key), cls, self._esc(value)))

    def line(self, text, cls="v"):
        self._put('<p><span class="%s">%s</span></p>' % (cls, self._esc(text)))

    def sep(self):
        self._put('<p><span class="d">%s</span></p>' % ("─" * 46))

    def response(self, text):
        """响应块：标题 + 逐行正文"""
        self._put('<p><span class="k">响应：</span></p>')
        body = (text or "").strip()
        if not body:
            self._put('<p><span class="w">(空响应)</span></p>')
            return
        for ln in body.splitlines():
            self._put('<p><span class="r">%s</span></p>' % self._esc(ln))

    def clear_log(self):
        self.view.clear()


class RootWidget(QWidget):
    """Transparent root: paints the window's outer neon glow."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        grad = QRadialGradient(rect.center(), rect.width() / 1.4)
        glow = QColor(C_CYAN)
        glow.setAlpha(46)
        grad.setColorAt(0.0, glow)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 16, 16)


class WindowFrame(QFrame):
    """Main frame: dark gradient + grid + radial glow + rounded neon border."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        base = QLinearGradient(r.topLeft(), r.bottomRight())
        base.setColorAt(0.0, QColor(9, 13, 30))
        base.setColorAt(0.5, QColor(13, 20, 42))
        base.setColorAt(1.0, QColor(7, 10, 24))
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.fillPath(path, QBrush(base))

        p.save()
        p.setClipPath(path)
        grid = QPen(QColor(0, 229, 255, 14))
        grid.setWidth(1)
        p.setPen(grid)
        step = 32
        x = int(r.left())
        while x < r.right():
            p.drawLine(x, int(r.top()), x, int(r.bottom()))
            x += step
        y = int(r.top())
        while y < r.bottom():
            p.drawLine(int(r.left()), y, int(r.right()), y)
            y += step
        p.restore()

        halo = QRadialGradient(r.center(), r.width() / 1.2)
        hc = QColor(C_CYAN)
        hc.setAlpha(24)
        halo.setColorAt(0.0, hc)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(halo))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 14, 14)

        edge = QPen(QColor(0, 229, 255, 110))
        edge.setWidth(1)
        p.setPen(edge)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 14, 14)


class TitleBar(QWidget):
    """Custom frameless title bar with pin / minimize / close."""

    def __init__(self, parent=None, title=APP_NAME):
        super().__init__(parent)
        self._win = parent
        self._drag = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(8)

        self.dot = StatusDot(self)
        self.title = QLabel(title)
        self.title.setObjectName("h1")
        self.sub = QLabel("v%s" % APP_VERSION)
        self.sub.setObjectName("sub")

        self.pin = QToolButton(self)
        self.pin.setObjectName("titleBtn")
        self.pin.setText("置顶")
        self.pin.setCheckable(True)
        self.pin.setCursor(Qt.PointingHandCursor)
        if self._win is not None:
            self.pin.toggled.connect(self._win.toggle_pin)

        self.btn_min = QToolButton(self)
        self.btn_min.setObjectName("titleBtn")
        self.btn_min.setText("—")
        self.btn_min.setCursor(Qt.PointingHandCursor)
        if self._win is not None:
            self.btn_min.clicked.connect(self._win.showMinimized)

        self.btn_close = QToolButton(self)
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setText("✕")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        if self._win is not None:
            self.btn_close.clicked.connect(self._win.close)

        lay.addWidget(self.dot)
        lay.addWidget(self.title)
        lay.addWidget(self.sub)
        lay.addStretch(1)
        lay.addWidget(self.pin)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._win is not None:
            self._drag = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and self._win is not None and (event.buttons() & Qt.LeftButton):
            self._win.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)


class HistoryRow(QWidget):
    """One history row: info + a per-row delete button."""

    def __init__(self, item, on_delete=None, parent=None):
        super().__init__(parent)
        self.item = item
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)

        ts = str(item.get("time", ""))
        url = str(item.get("url", ""))
        ok = bool(item.get("ok", False))
        cnt = item.get("count", 0)
        ms = item.get("ms", 0)

        self.time = QLabel(ts)
        self.time.setObjectName("caption")
        self.time.setFixedWidth(140)

        self.info = QLabel("%s · %s 个模型 · %.0f ms" % (url, cnt, ms or 0))
        self.info.setObjectName("statName")

        self.flag = QLabel("检测成功" if ok else "检测失败")
        self.flag.setObjectName("caption")
        self.flag.setStyleSheet("color: %s;" % (C_GREEN if ok else C_RED))

        self.btn = QPushButton("✕")
        self.btn.setObjectName("dangerBtn")
        self.btn.setFixedWidth(34)
        self.btn.setToolTip("删除此条记录")
        self.btn.setCursor(Qt.PointingHandCursor)
        if on_delete is not None:
            self.btn.clicked.connect(lambda: on_delete(self.item))

        lay.addWidget(self.time)
        lay.addWidget(self.flag)
        lay.addWidget(self.info, 1)
        lay.addWidget(self.btn)


class HistoryDialog(QDialog):
    """History viewer: per-row delete and clear-all."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查询历史")
        self.resize(720, 460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.list = QListWidget()
        self.list.setObjectName("historyList")
        outer.addWidget(self.list, 1)

        bar = QHBoxLayout()
        self.lbl = QLabel("")
        self.lbl.setObjectName("footer")
        self.btn_del = QPushButton("删除选中")
        self.btn_del.setObjectName("dangerBtn")
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_clear = QPushButton("一键清空")
        self.btn_clear.setObjectName("dangerBtn")
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("ghostBtn")
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.lbl, 1)
        bar.addWidget(self.btn_del)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_close)
        outer.addLayout(bar)

        self._reload()

    def _reload(self):
        self.list.clear()
        items = load_history()
        for it in items:
            row = HistoryRow(it, on_delete=self._delete_row)
            q = QListWidgetItem(self.list)
            q.setSizeHint(row.sizeHint())
            self.list.addItem(q)
            self.list.setItemWidget(q, row)
        self.lbl.setText("共 %d 条记录 · 点击行尾 ✕ 或选中后点「删除选中」可单条删除" % len(items))
        if not items:
            self.list.addItem(QListWidgetItem("暂无历史记录"))

    def _delete_row(self, item):
        items = [x for x in load_history() if x != item]
        save_history(items)
        self._reload()

    def delete_selected(self):
        row = self.list.currentRow()
        if row < 0:
            return
        items = load_history()
        if 0 <= row < len(items):
            del items[row]
            save_history(items)
        self._reload()

    def clear_all(self):
        save_history([])
        self._reload()


class MainWindow(QMainWindow):
    """Main window: connection config, one-click / batch detection, history."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(1000, 820)
        self.setMinimumSize(780, 620)

        self.cfg = load_config()
        self.models = []
        self._busy = False
        self._busy_n = 0
        self._pending = []
        self._active = 0
        self._rows = {}
        self._results = {}
        self._workers = []
        self._log_multi = False

        root = RootWidget(self)
        self.setCentralWidget(root)

        self._busy_timer = QTimer(self)
        self._busy_timer.timeout.connect(self._busy_tick)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(8, 8, 8, 8)

        self.frame = WindowFrame(root)
        self.frame.setObjectName("glass")
        rl.addWidget(self.frame)
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        self.titlebar = TitleBar(self, APP_NAME)
        fl.addWidget(self.titlebar)

        body = QWidget(self.frame)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 8, 18, 14)
        bl.setSpacing(12)

        head = QLabel("▍连接配置  CONNECTION")
        head.setObjectName("groupHeader")
        bl.addWidget(head)

        form = QHBoxLayout()
        form.setSpacing(10)
        self.ed_url = QLineEdit(self.cfg.get("base_url", ""))
        self.ed_url.setPlaceholderText("http://localhost:8082/v1")
        self.ed_key = QLineEdit(self.cfg.get("api_key", ""))
        self.ed_key.setPlaceholderText("sk-... (模型测试必须填写有效 Key)")
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.btn_eye = QPushButton("显示")
        self.btn_eye.setObjectName("ghostBtn")
        self.btn_eye.setFixedWidth(64)
        self.btn_eye.clicked.connect(self._toggle_key)
        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(1, 600)
        self.sp_timeout.setValue(int(self.cfg.get("timeout", 15)))
        self.sp_conf = QSpinBox()
        self.sp_conf.setRange(1, 32)
        self.sp_conf.setValue(int(self.cfg.get("test_concurrency", 3)))
        self.sp_conf.setToolTip("批量测试时的最大并发请求数")
        self.sp_maxtok = QSpinBox()
        self.sp_maxtok.setRange(1, 8192)
        self.sp_maxtok.setValue(int(self.cfg.get("max_tokens", 64)))
        self.sp_maxtok.setToolTip("测试请求的 max_tokens：设大一点才能看出模型是否完整回话")
        form.addWidget(QLabel("BASE URL"))
        form.addWidget(self.ed_url, 3)
        form.addWidget(QLabel("API Key"))
        form.addWidget(self.ed_key, 2)
        form.addWidget(self.btn_eye)
        form.addWidget(QLabel("超时"))
        form.addWidget(self.sp_timeout)
        form.addWidget(QLabel("并发数"))
        form.addWidget(self.sp_conf)
        form.addWidget(QLabel("回复上限"))
        form.addWidget(self.sp_maxtok)
        bl.addLayout(form)

        self.btn_detect = DetectButton("⚡  一 键 检 测")
        self.btn_detect.clicked.connect(self.start_detect)
        bl.addWidget(self.btn_detect)

        bar = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("🔍  搜索模型 ID ...")
        self.ed_search.textChanged.connect(self.apply_filter)
        self.btn_all = QPushButton("⚡ 全部测试")
        self.btn_all.setObjectName("ghostBtn")
        self.btn_all.clicked.connect(self.test_all)
        self.btn_copy_all = QPushButton("复制全部")
        self.btn_copy_all.setObjectName("ghostBtn")
        self.btn_copy_all.clicked.connect(self.copy_all)
        self.btn_export = QPushButton("导出 ▾")
        self.btn_export.setObjectName("ghostBtn")
        self.btn_export.clicked.connect(self.export_results)
        self.btn_cfg = QPushButton("配置 ▾")
        self.btn_cfg.setObjectName("ghostBtn")
        self.btn_cfg.setToolTip("一键导入 / 导出配置（BASE URL、Key、超时、并发、别名等）")
        self.btn_cfg.clicked.connect(self.show_config_menu)
        self.btn_hist = QPushButton("历史")
        self.btn_hist.setObjectName("ghostBtn")
        self.btn_hist.clicked.connect(self.show_history)
        self.btn_log = QPushButton("日志")
        self.btn_log.setObjectName("ghostBtn")
        self.btn_log.setCheckable(True)
        self.btn_log.setChecked(True)
        self.btn_log.setToolTip("显示 / 隐藏下方测试日志面板")
        self.btn_log.toggled.connect(self._toggle_logpanel)
        bar.addWidget(self.ed_search, 1)
        bar.addWidget(self.btn_all)
        bar.addWidget(self.btn_copy_all)
        bar.addWidget(self.btn_export)
        bar.addWidget(self.btn_cfg)
        bar.addWidget(self.btn_hist)
        bar.addWidget(self.btn_log)
        bl.addLayout(bar)

        self.list = QListWidget()
        self.list.setObjectName("modelList")
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)

        self.logpanel = LogPanel(self)
        self.logpanel.ed_alias.setText(self.cfg.get("account_alias", "") or "")
        show_log = bool(self.cfg.get("show_log", True))
        self.logpanel.setVisible(show_log)
        self.btn_log.setChecked(show_log)

        self.split = QSplitter(Qt.Vertical)
        self.split.setObjectName("mainSplit")
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.list)
        self.split.addWidget(self.logpanel)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setSizes([400, 230])
        bl.addWidget(self.split, 1)

        self.status = QLabel("就绪")
        self.status.setObjectName("footer")
        bl.addWidget(self.status)

        fl.addWidget(body, 1)

        self._shortcut = QShortcut(QKeySequence("F5"), self)
        self._shortcut.activated.connect(self.start_detect)

        self.frame.setGraphicsEffect(self._shadow())
        self._placeholder()
        if self.cfg.get("always_on_top"):
            self.titlebar.pin.setChecked(True)

    def _shadow(self):
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(38)
        eff.setOffset(0, 8)
        eff.setColor(QColor(0, 229, 255, 70))
        return eff

    def _stat_name(self, key):
        return {"models": "模型数", "latency": "上次检测"}.get(key, key)

    def _center(self):
        geo = self.frameGeometry()
        geo.moveCenter(QApplication.primaryScreen().availableGeometry().center())
        self.move(geo.topLeft())

    def toggle_pin(self, on):
        flags = self.windowFlags()
        if on:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _toggle_key(self):
        if self.ed_key.echoMode() == QLineEdit.Password:
            self.ed_key.setEchoMode(QLineEdit.Normal)
            self.btn_eye.setText("隐藏")
        else:
            self.ed_key.setEchoMode(QLineEdit.Password)
            self.btn_eye.setText("显示")

    def save_config(self):
        self.cfg["base_url"] = self.ed_url.text().strip()
        self.cfg["api_key"] = self.ed_key.text().strip()
        self.cfg["timeout"] = int(self.sp_timeout.value())
        self.cfg["test_concurrency"] = int(self.sp_conf.value())
        self.cfg["always_on_top"] = bool(self.titlebar.pin.isChecked())
        self.cfg["account_alias"] = self.logpanel.ed_alias.text().strip()
        self.cfg["max_tokens"] = int(self.sp_maxtok.value())
        self.cfg["show_log"] = bool(self.btn_log.isChecked())
        if save_config_data(self.cfg):
            self.toast("配置已保存")
        else:
            self.toast("配置保存失败")

    def _toggle_logpanel(self, on):
        """显示 / 隐藏测试日志面板，并记住选择。"""
        self.logpanel.setVisible(bool(on))
        if on:
            self.split.setSizes([400, 230])
        self.cfg["show_log"] = bool(on)
        save_config_data(self.cfg)

    # ---------- 配置一键导入 / 导出 ----------

    def show_config_menu(self):
        menu = QMenu(self)
        act_exp = menu.addAction("导出配置为 JSON 文件 ...")
        act_imp = menu.addAction("从 JSON 文件导入配置 ...")
        menu.addSeparator()
        act_copy = menu.addAction("复制配置到剪贴板")
        act_paste = menu.addAction("从剪贴板粘贴配置")
        menu.addSeparator()
        act_reset = menu.addAction("恢复默认配置")
        act = menu.exec(self.btn_cfg.mapToGlobal(self.btn_cfg.rect().bottomLeft()))
        if act is act_exp:
            self.export_config_json()
        elif act is act_imp:
            self.import_config_json()
        elif act is act_copy:
            self.copy_config_json()
        elif act is act_paste:
            self.paste_config_json()
        elif act is act_reset:
            self.reset_config()

    def _config_payload(self):
        """当前配置 → 可序列化字典（含 API Key）。"""
        self._save_now()
        return {
            "app": APP_NAME,
            "kind": "config",
            "version": APP_VERSION,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "此文件包含 API Key，请妥善保管",
            "config": {k: self.cfg.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG},
        }

    def export_config_json(self):
        default = "一键测API-配置-%s.json" % datetime.now().strftime("%Y%m%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", default, "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config_payload(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            self.toast("导出失败: %s" % e)
            return
        self.toast("配置已导出: " + os.path.basename(path))

    def import_config_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "", "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            self.toast("导入失败: %s" % e)
            return
        self._apply_imported(data, os.path.basename(path))

    def copy_config_json(self):
        text = json.dumps(self._config_payload(), ensure_ascii=False, indent=2)
        QApplication.clipboard().setText(text)
        self.toast("配置 JSON 已复制到剪贴板")

    def paste_config_json(self):
        text = QApplication.clipboard().text() or ""
        if not text.strip():
            self.toast("剪贴板为空")
            return
        try:
            data = json.loads(text)
        except ValueError:
            self.toast("剪贴板内容不是有效 JSON")
            return
        self._apply_imported(data, "剪贴板")

    def reset_config(self):
        self.cfg = dict(DEFAULT_CONFIG)
        self._apply_cfg_to_ui()
        save_config_data(self.cfg)
        self.toast("已恢复默认配置")

    @staticmethod
    def _parse_config_payload(data):
        """接受 {config:{...}} 包装形式或裸配置；逐字段校验类型，非法项丢弃。"""
        if not isinstance(data, dict):
            return {}
        src = data.get("config")
        if not isinstance(src, dict):
            src = data
        out = {}
        for key, raw in src.items():
            if key not in DEFAULT_CONFIG:
                continue
            want = type(DEFAULT_CONFIG[key])
            if want is bool:
                if isinstance(raw, bool):
                    out[key] = raw
                elif isinstance(raw, str):
                    out[key] = raw.strip().lower() in ("1", "true", "yes", "on")
            elif want is int:
                if isinstance(raw, bool):
                    continue
                if isinstance(raw, (int, float)):
                    out[key] = int(raw)
                elif isinstance(raw, str) and raw.strip().lstrip("+-").isdigit():
                    out[key] = int(raw.strip())
            elif want is str:
                if isinstance(raw, str):
                    out[key] = raw
        return out

    def _apply_imported(self, data, source):
        got = self._parse_config_payload(data)
        if not got:
            self.toast("导入失败: 未识别到配置字段")
            return
        if "base_url" in got and not str(got.get("base_url", "")).strip():
            self.toast("导入失败: base_url 为空")
            return
        for k, v in got.items():
            self.cfg[k] = v
        self._apply_cfg_to_ui()
        save_config_data(self.cfg)
        self.toast("已从 %s 导入 %d 项配置" % (source, len(got)))

    def _apply_cfg_to_ui(self):
        """把 self.cfg 写回界面控件。"""
        self.ed_url.setText(str(self.cfg.get("base_url", "")))
        self.ed_key.setText(str(self.cfg.get("api_key", "")))
        self.sp_timeout.setValue(int(self.cfg.get("timeout", 15)))
        self.sp_conf.setValue(int(self.cfg.get("test_concurrency", 3)))
        self.sp_maxtok.setValue(int(self.cfg.get("max_tokens", 64)))
        self.logpanel.ed_alias.setText(str(self.cfg.get("account_alias", "") or ""))

        pin = bool(self.cfg.get("always_on_top"))
        if self.titlebar.pin.isChecked() != pin:
            self.titlebar.pin.setChecked(pin)

        show_log = bool(self.cfg.get("show_log", True))
        if self.btn_log.isChecked() != show_log:
            self.btn_log.setChecked(show_log)   # 会触发 _toggle_logpanel
        else:
            self.logpanel.setVisible(show_log)

    def start_detect(self):
        url = self.ed_url.text().strip()
        if not url:
            self.toast("请先填写 BASE URL")
            return
        self._save_now()
        self._set_busy(True)
        self.titlebar.dot.set_status("busy")
        self._set_status("正在检测")
        self.btn_detect.setText("检 测 中")
        self.list.clear()
        self.models = []
        self._rows = {}
        self._results = {}

        w = ApiWorker(url, self.ed_key.text().strip(), int(self.sp_timeout.value()))
        w.succeeded.connect(self._on_success)
        w.failed.connect(self._on_failure)
        w.finished.connect(self._detect_done)
        self._workers.append(w)
        w.start()

    def _detect_done(self):
        self._set_busy(False)
        self.btn_detect.setText("⚡  一 键 检 测")

    def _save_now(self):
        self.cfg["base_url"] = self.ed_url.text().strip()
        self.cfg["api_key"] = self.ed_key.text().strip()
        self.cfg["timeout"] = int(self.sp_timeout.value())
        self.cfg["test_concurrency"] = int(self.sp_conf.value())
        self.cfg["account_alias"] = self.logpanel.ed_alias.text().strip()
        self.cfg["max_tokens"] = int(self.sp_maxtok.value())
        self.cfg["show_log"] = bool(self.btn_log.isChecked())
        self.cfg["always_on_top"] = bool(self.titlebar.pin.isChecked())
        save_config_data(self.cfg)

    def _set_busy(self, busy):
        self._busy = busy
        self.btn_detect.setEnabled(not busy)
        self.btn_all.setEnabled(not busy)
        if busy:
            self._busy_n = 0
            self._busy_timer.start(80)
        else:
            self._busy_timer.stop()

    def _busy_tick(self):
        self._busy_n = (self._busy_n + 1) % 4
        self.btn_detect.setText("检 测 中" + "." * self._busy_n)

    def _set_status(self, text):
        self.status.setText(text)

    def _on_success(self, models, ms):
        self.models = models
        self._results = {}
        self.titlebar.dot.set_status("ok")
        self._set_status("检测成功 · %d 个模型 · %.0f ms" % (len(models), ms))
        self._populate_list()
        self._record_history(True, len(models), ms)

    def _on_failure(self, tag, detail):
        self.titlebar.dot.set_status("error")
        self._set_status("检测失败: " + str(tag))
        self.toast("检测失败: %s" % tag)
        self._placeholder()
        self._record_history(False, 0, 0)

    def _record_history(self, ok, count, ms):
        items = load_history()
        items.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": self.ed_url.text().strip(),
            "ok": bool(ok),
            "count": int(count),
            "ms": float(ms or 0),
        })
        save_history(items[:200])

    # ---------- 日志 ----------

    def _account_name(self):
        """日志里显示的账号名：优先用别名，否则退到 BASE URL 主机名。"""
        alias = (self.logpanel.ed_alias.text() or "").strip()
        if alias:
            return alias
        url = (self.ed_url.text() or "").strip()
        host = url.split("//")[-1].split("/")[0] if url else ""
        return host or "未命名账号"

    def _start_log(self, model_id):
        """开一条日志：单测打完整链路，批量不打头部（结果行自带模型名）。"""
        if self._log_multi:
            return
        lp = self.logpanel
        lp.sep()
        lp.kv("开始测试账号：", self._account_name())
        lp.kv("账号类型：", "apikey")
        lp.kv("使用模型：", model_id)

    def _on_test_progress(self, model_id, event, payload):
        # 批量模式下多个 worker 并发，过程行会相互交错、无法归属到具体模型，
        # 因此只保留最终结果行；完整链路仅在单个测试时展开。
        if self._log_multi:
            return
        lp = self.logpanel
        if event == "sending":
            lp.kv("发送测试消息：", '"%s"' % payload)
        elif event == "connected":
            lp.line("已连接到 API")
        elif event == "response":
            lp.response(payload)

    def test_model(self, model_id, batch=False):
        if not self.ed_key.text().strip():
            self.toast("测试模型需要填写 API Key")
            return
        self._log_multi = bool(batch)
        row = self._rows.get(model_id)
        if row is not None:
            row.set_testing()
        self._set_status("测试中...")
        self._start_log(model_id)
        w = ModelTestWorker(
            self.ed_url.text().strip(),
            self.ed_key.text().strip(),
            model_id,
            int(self.cfg.get("test_timeout", 30)),
            int(self.sp_maxtok.value()),
        )
        w.progress.connect(self._on_test_progress)
        w.succeeded.connect(self._on_test_success)
        w.failed.connect(self._on_test_failure)
        w.finished.connect(self._on_test_thread_finished)
        self._workers.append(w)
        w.start()

    def test_all(self):
        if not self.ed_key.text().strip():
            self.toast("批量测试需要填写 API Key")
            return
        if not self.models:
            self.toast("暂无可导出的结果，请先检测")
            return
        if self._active:
            self.toast("所有模型正在测试中")
            return
        n = max(1, int(self.sp_conf.value()))
        self._pending = [m["id"] for m in self.models]
        self._log_multi = True
        lp = self.logpanel
        lp.sep()
        lp.kv("开始批量测试账号：", self._account_name())
        lp.kv("账号类型：", "apikey")
        lp.kv("并发数：", str(n))
        lp.line("共 %d 个模型待测" % len(self._pending))
        self.toast("开始批量测试 %d 个模型（最多 %d 并发）" % (len(self._pending), n))
        self._pump_test_queue()

    def _pump_test_queue(self):
        n = max(1, int(self.sp_conf.value()))
        while self._pending and self._active < n:
            mid = self._pending.pop(0)
            self._active += 1
            self.test_model(mid, batch=True)

    def _on_test_success(self, model_id, ms):
        self._results[model_id] = ms
        row = self._rows.get(model_id)
        if row is not None:
            row.set_result(ms)
        if self._log_multi:
            self.logpanel.line("  ✓ %s  ·  %.0f ms" % (model_id, ms), "r")
        else:
            self.logpanel.sep()
            self.logpanel.line("✓ 测试完成!   响应 %.0f ms" % ms, "r")

    def _on_test_failure(self, model_id, tag, detail):
        self._results[model_id] = tag
        row = self._rows.get(model_id)
        if row is not None:
            row.set_error(tag)
        if self._log_multi:
            self.logpanel.line("  ✗ %s  ·  %s" % (model_id, tag), "e")
        else:
            self.logpanel.sep()
            self.logpanel.line("✗ 测试失败: %s" % tag, "e")
            if detail:
                for ln in str(detail).splitlines():
                    self.logpanel.line(ln, "e")

    def _on_test_thread_finished(self):
        self._active = max(0, self._active - 1)
        if self._pending:
            self._pump_test_queue()
        elif self._active == 0:
            ok = sum(1 for v in self._results.values() if isinstance(v, float))
            msg = "批量测试完成: %d/%d 成功" % (ok, len(self.models))
            if self._log_multi:
                self.logpanel.sep()
                self.logpanel.line("✓ " + msg if ok else "✗ " + msg,
                                   "r" if ok else "e")
            self._log_multi = False
            self.toast(msg)
            self._set_status(msg)

    def _cancel_all_tests(self):
        self._pending = []
        for w in list(self._workers):
            try:
                if w.isRunning():
                    w.terminate()
                    w.wait(500)
            except Exception:
                pass
        self._workers = []
        self._active = 0

    def _placeholder(self):
        self.list.clear()
        q = QListWidgetItem("点击「一键检测」获取可用模型列表")
        q.setTextAlignment(Qt.AlignCenter)
        self.list.addItem(q)
        q2 = QListWidgetItem("支持 OpenAI 兼容接口: GET {BASE URL}/models")
        q2.setTextAlignment(Qt.AlignCenter)
        self.list.addItem(q2)
        q3 = QListWidgetItem("检测后点击每个模型右侧「测试」按钮可测响应时间")
        q3.setTextAlignment(Qt.AlignCenter)
        self.list.addItem(q3)

    def _populate_list(self):
        self.list.clear()
        self._rows = {}
        for i, m in enumerate(self.models, 1):
            row = ModelRow(i, m, on_test=self.test_model)
            item = QListWidgetItem(self.list)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self._rows[m["id"]] = row

    def apply_filter(self, text):
        needle = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            wdg = self.list.itemWidget(item)
            if wdg is None:
                continue
            mid = getattr(wdg, "model_id", "")
            item.setHidden(bool(needle) and needle not in mid.lower())

    def copy_model(self, model_id):
        QApplication.clipboard().setText(model_id)
        self.toast("已复制: " + model_id)

    def copy_all(self):
        if not self.models:
            self.toast("暂无可复制的模型")
            return
        text = "\n".join(m["id"] for m in self.models)
        QApplication.clipboard().setText(text)
        self._copy_item(len(self.models))

    def _copy_item(self, n):
        self.toast("已复制 %d 个模型 ID" % n)

    def export_results(self):
        if not self.models:
            self.toast("暂无可导出的结果，请先检测")
            return
        menu = QMenu(self)
        act_csv = menu.addAction("导出 CSV（表格）")
        act_json = menu.addAction("导出 JSON（完整数据）")
        act_txt = menu.addAction("导出 TXT（纯模型 ID）")
        act = menu.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))
        if act is act_csv:
            self._export("csv")
        elif act is act_json:
            self._export("json")
        elif act is act_txt:
            self._export("txt")

    def _export(self, kind):
        if kind == "csv":
            filt = "CSV 文件 (*.csv)"
            default = "models.csv"
        elif kind == "json":
            filt = "JSON 文件 (*.json)"
            default = "models.json"
        else:
            filt = "文本文件 (*.txt)"
            default = "models.txt"
        path, _ = QFileDialog.getSaveFileName(self, "导出模型列表", default, filt)
        if not path:
            return
        try:
            if kind == "csv":
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    wr = csv.writer(f)
                    wr.writerow(["#", "model", "owned_by", "latency_ms"])
                    for i, m in enumerate(self.models, 1):
                        v = self._results.get(m["id"], "")
                        wr.writerow([i, m["id"], m.get("owned_by", ""),
                                     v if isinstance(v, float) else ""])
            elif kind == "json":
                rows = []
                for i, m in enumerate(self.models, 1):
                    v = self._results.get(m["id"], None)
                    rows.append({
                        "index": i,
                        "id": m["id"],
                        "owned_by": m.get("owned_by", ""),
                        "family": family_of(m["id"]),
                        "latency_ms": v if isinstance(v, float) else None,
                        "status": "ok" if isinstance(v, float) else (v or "untested"),
                    })
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"url": self.ed_url.text().strip(),
                               "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "models": rows}, f, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for m in self.models:
                        f.write(m["id"] + "\n")
            self.toast("已导出: " + os.path.basename(path))
        except OSError as e:
            self.toast("导出失败: %s" % e)

    def show_history(self):
        HistoryDialog(self).exec()

    def toast(self, text):
        lbl = QLabel(text, self)
        lbl.setObjectName("footer")
        lbl.setStyleSheet(
            "background-color: rgba(5, 9, 22, 235);"
            "border: 1px solid rgba(0, 229, 255, 110);"
            "border-radius: 10px; padding: 8px 16px; color: #d9e6ff;")
        lbl.adjustSize()
        lbl.move((self.width() - lbl.width()) // 2, self.height() - 90)
        eff = QGraphicsOpacityEffect(lbl)
        lbl.setGraphicsEffect(eff)
        lbl.show()
        lbl.raise_()
        QTimer.singleShot(1600, lambda: self._toast_out(lbl))

    def _toast_out(self, lbl):
        try:
            lbl.deleteLater()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self._save_now()
            self._cancel_all_tests()
        finally:
            super().closeEvent(event)


def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(GLOBAL_QSS)
    app.setWindowIcon(QIcon(make_app_pixmap()))
    win = MainWindow()
    win.show()
    win._center()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        with open(os.path.join(app_dir(), "error.log"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise
