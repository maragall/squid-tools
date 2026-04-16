"""Cephla-branded global stylesheet for squid-tools.

Color palette from cephla-downloads.pages.dev:
  Background primary:   #353535 (graphite)
  Background secondary: #2a2a2a (dark graphite)
  Text primary:         #ffffff (white)
  Text secondary:       #aaaaaa (light gray)
  Text body:            #cccccc (light gray)
  Accent:               #2A82DA (Cephla blue)
  Border:               #444444 (dark gray)

Minimal. The data is the centerpiece, not the chrome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

CEPHLA_STYLESHEET = """
/* Global */
* {
    font-family: "Segoe UI", "Helvetica Neue", "Arial", sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background-color: #353535;
    color: #cccccc;
}

/* Labels */
QLabel {
    color: #ffffff;
    background: transparent;
}

/* Buttons */
QPushButton {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 6px 16px;
    min-height: 20px;
}
QPushButton:hover {
    border-color: #2A82DA;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #2A82DA;
    color: #ffffff;
}
QPushButton:checked {
    background-color: #2A82DA;
    color: #ffffff;
    border-color: #2A82DA;
}
QPushButton:disabled {
    opacity: 0.4;
    color: #666666;
}

/* Tabs */
QTabWidget::pane {
    border: none;
    background-color: #353535;
}
QTabBar::tab {
    background-color: #2a2a2a;
    color: #aaaaaa;
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #ffffff;
    border-bottom: 2px solid #2A82DA;
}
QTabBar::tab:hover {
    color: #ffffff;
}

/* Sliders */
QSlider::groove:horizontal {
    background: #444444;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #2A82DA;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #2A82DA;
    border-radius: 2px;
}

/* Checkboxes */
QCheckBox {
    color: #cccccc;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #444444;
    background: #2a2a2a;
}
QCheckBox::indicator:checked {
    background: #2A82DA;
    border-color: #2A82DA;
}

/* Combo boxes */
QComboBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 4px 8px;
}
QComboBox:hover {
    border-color: #2A82DA;
}
QComboBox::drop-down {
    border: none;
    background: #2a2a2a;
}

/* Spin boxes */
QSpinBox, QDoubleSpinBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
    padding: 2px 6px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #2A82DA;
}

/* Splitters */
QSplitter::handle {
    background: #444444;
    width: 1px;
}

/* Scroll bars */
QScrollBar:vertical {
    background: #2a2a2a;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #444444;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #2A82DA;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Menu bar */
QMenuBar {
    background-color: #2a2a2a;
    color: #cccccc;
}
QMenuBar::item:selected {
    background-color: #2A82DA;
    color: #ffffff;
}
QMenu {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #444444;
}
QMenu::item:selected {
    background-color: #2A82DA;
    color: #ffffff;
}

/* Tooltips */
QToolTip {
    background-color: #2a2a2a;
    color: #ffffff;
    border: 1px solid #444444;
    padding: 4px;
}

/* Form layout labels */
QFormLayout QLabel {
    color: #aaaaaa;
}
"""


def apply_style(app: QApplication) -> None:
    """Apply the Cephla-branded stylesheet to the application."""
    app.setStyleSheet(CEPHLA_STYLESHEET)
