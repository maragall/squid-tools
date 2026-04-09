"""Minimal graphite theme for squid-tools GUI.

Follows ndviewer-light's visual language: monochromatic grays,
white text, blue only on the Cephla logo and subtle hover accents.
"""
from __future__ import annotations

CEPHLA_BLUE = "#31c4f3"

BG_DARK = "#2a2a2a"
BG_MEDIUM = "#353535"
BG_LIGHT = "#3f3f3f"
BG_INPUT = "#444444"
BORDER = "#444444"
BORDER_HOVER = "#2A82DA"
TEXT = "#cccccc"
TEXT_BRIGHT = "#ffffff"
TEXT_DIM = "#aaaaaa"
TEXT_DISABLED = "#666666"

FONT_FAMILY = "Helvetica Neue, Segoe UI, Arial, sans-serif"

STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
}}

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
    background-color: {BG_LIGHT};
    color: {TEXT_BRIGHT};
}}

QMenu {{
    background-color: {BG_MEDIUM};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {BG_LIGHT};
    color: {TEXT_BRIGHT};
}}

QPushButton {{
    background-color: {BG_MEDIUM};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    background-color: {BG_LIGHT};
    border-color: {BORDER_HOVER};
    color: {TEXT_BRIGHT};
}}
QPushButton:pressed {{
    background-color: {BG_INPUT};
}}
QPushButton:checked {{
    background-color: {BG_LIGHT};
    border-color: {BORDER_HOVER};
    color: {TEXT_BRIGHT};
}}
QPushButton:disabled {{
    background-color: {BG_DARK};
    color: {TEXT_DISABLED};
    border-color: {BG_MEDIUM};
}}

QGroupBox {{
    background-color: {BG_MEDIUM};
    border: 1px solid {BORDER};
    border-radius: 3px;
    margin-top: 12px;
    padding-top: 14px;
    color: {TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {TEXT_DIM};
}}

QTabWidget::pane {{
    background-color: {BG_MEDIUM};
    border: 1px solid {BORDER};
    border-top: none;
}}
QTabBar::tab {{
    background-color: {BG_DARK};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 1px;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
}}
QTabBar::tab:selected {{
    background-color: {BG_MEDIUM};
    color: {TEXT_BRIGHT};
}}
QTabBar::tab:hover:!selected {{
    background-color: {BG_LIGHT};
    color: {TEXT};
}}

QLabel {{
    color: {TEXT};
}}

QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 8px;
}}
QComboBox:focus {{
    border-color: {BORDER_HOVER};
}}
QComboBox::drop-down {{
    border: none;
    background-color: {BG_LIGHT};
    width: 20px;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {BORDER_HOVER};
}}

QCheckBox {{
    color: {TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 2px;
    background-color: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background-color: {TEXT_DIM};
    border-color: {TEXT_DIM};
}}

QScrollBar:vertical {{
    background-color: {BG_DARK};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QToolTip {{
    background-color: {BG_MEDIUM};
    color: {TEXT_BRIGHT};
    border: 1px solid {BORDER};
    padding: 4px;
}}
"""
