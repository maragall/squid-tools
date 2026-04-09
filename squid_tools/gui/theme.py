"""Graphite theme with Cephla blue accents for squid-tools GUI."""
from __future__ import annotations

# Cephla brand blue from logo SVG
CEPHLA_BLUE = "#31c4f3"
CEPHLA_BLUE_HOVER = "#45d0f7"
CEPHLA_BLUE_PRESSED = "#1fb0e0"

# Graphite palette
BG_DARK = "#2b2b2b"
BG_MEDIUM = "#353535"
BG_LIGHT = "#3f3f3f"
BG_INPUT = "#454545"
BORDER = "#555555"
BORDER_FOCUS = CEPHLA_BLUE
TEXT = "#e0e0e0"
TEXT_DIM = "#999999"
TEXT_DISABLED = "#666666"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT};
}}

QMenuBar {{
    background-color: {BG_MEDIUM};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{
    background-color: {CEPHLA_BLUE};
    color: white;
}}

QMenu {{
    background-color: {BG_MEDIUM};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {CEPHLA_BLUE};
    color: white;
}}

QPushButton {{
    background-color: {CEPHLA_BLUE};
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {CEPHLA_BLUE_HOVER};
}}
QPushButton:pressed {{
    background-color: {CEPHLA_BLUE_PRESSED};
}}
QPushButton:checked {{
    background-color: {CEPHLA_BLUE_PRESSED};
    border: 2px solid {CEPHLA_BLUE};
}}
QPushButton:disabled {{
    background-color: {BG_INPUT};
    color: {TEXT_DISABLED};
}}

QGroupBox {{
    background-color: {BG_MEDIUM};
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: {TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {CEPHLA_BLUE};
}}

QTabWidget::pane {{
    background-color: {BG_MEDIUM};
    border: 1px solid {BORDER};
    border-top: none;
}}
QTabBar::tab {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {CEPHLA_BLUE};
    color: white;
    font-weight: bold;
}}
QTabBar::tab:hover:!selected {{
    background-color: {BG_INPUT};
    color: {TEXT};
}}

QLabel {{
    color: {TEXT};
}}

QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
}}
QComboBox:focus {{
    border-color: {CEPHLA_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    background-color: {CEPHLA_BLUE};
    width: 20px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {CEPHLA_BLUE};
}}

QCheckBox {{
    color: {TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background-color: {CEPHLA_BLUE};
    border-color: {CEPHLA_BLUE};
}}

QScrollBar:vertical {{
    background-color: {BG_DARK};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {CEPHLA_BLUE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QToolTip {{
    background-color: {BG_MEDIUM};
    color: {TEXT};
    border: 1px solid {CEPHLA_BLUE};
    padding: 4px;
}}
"""
