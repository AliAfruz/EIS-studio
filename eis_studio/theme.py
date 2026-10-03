"""Application and plotting themes for EIS Gold Studio."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    name: str
    window: str
    panel: str
    panel_alt: str
    input_bg: str
    text: str
    muted_text: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    border: str
    grid: str
    plot_bg: str
    plot_text: str
    measured: str
    fit: str
    secondary: str
    negative: str


LIGHT_PALETTE = ThemePalette(
    name="light",
    window="#F2EEE5",
    panel="#FBFAF6",
    panel_alt="#EDE6D8",
    input_bg="#FFFFFF",
    text="#242722",
    muted_text="#6C706A",
    accent="#B98224",
    accent_hover="#D9A94B",
    accent_pressed="#976616",
    accent_text="#FFFFFF",
    border="#C8B990",
    grid="#C8C1B3",
    plot_bg="#FAFAF7",
    plot_text="#272B28",
    measured="#A66A13",
    fit="#167A84",
    secondary="#7656A5",
    negative="#A64545",
)

DARK_PALETTE = ThemePalette(
    name="dark",
    window="#07121B",
    panel="#111B26",
    panel_alt="#192634",
    input_bg="#0C1721",
    text="#EEF4F4",
    muted_text="#98A9AE",
    accent="#E8BD5E",
    accent_hover="#F4D37F",
    accent_pressed="#B9852B",
    accent_text="#17130B",
    border="#53616A",
    grid="#3C4B54",
    plot_bg="#0A141D",
    plot_text="#EAF2F2",
    measured="#F0C96A",
    fit="#65D8DE",
    secondary="#B89AE8",
    negative="#ED8D8D",
)

PALETTES = {"light": LIGHT_PALETTE, "dark": DARK_PALETTE}


def get_palette(theme_name: str) -> ThemePalette:
    """Return a safe palette for a user-provided theme name."""
    return PALETTES.get(str(theme_name).lower(), LIGHT_PALETTE)


def get_stylesheet(theme_name: str) -> str:
    """Build the translucent cinematic Qt style sheet."""
    p = get_palette(theme_name)
    dark = p.name == "dark"
    glass = "rgba(14, 25, 36, 218)" if dark else "rgba(255, 255, 255, 218)"
    glass_soft = "rgba(23, 37, 50, 188)" if dark else "rgba(250, 248, 242, 194)"
    glass_hover = "rgba(43, 61, 75, 222)" if dark else "rgba(255, 252, 242, 236)"
    input_glass = "rgba(6, 15, 23, 205)" if dark else "rgba(255, 255, 255, 226)"
    border = "rgba(191, 213, 219, 68)" if dark else "rgba(100, 88, 61, 54)"
    border_bright = "rgba(235, 198, 105, 142)" if dark else "rgba(166, 111, 22, 130)"
    menu_selected = "rgba(232, 189, 94, 48)" if dark else "rgba(185, 130, 36, 35)"
    disabled_bg = "rgba(35, 45, 52, 150)" if dark else "rgba(221, 217, 206, 170)"
    disabled_text = "#66747A" if dark else "#98978F"
    scrollbar_bg = "rgba(2, 8, 12, 82)" if dark else "rgba(129, 116, 86, 24)"
    scrollbar_handle = "rgba(232, 189, 94, 112)" if dark else "rgba(155, 110, 32, 92)"
    tooltip_bg = "#15232D" if dark else "#FFF9EA"
    group_title_bg = "#101B25" if dark else "#FBFAF6"
    cyan = "#65D8DE" if dark else "#167A84"
    selected_text = p.accent_text

    return f"""
QMainWindow {{ background: {p.window}; }}
QWidget {{
    color: {p.text};
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}}
QWidget#cinematicRoot, QWidget#heroCopy, QWidget#resultsPane {{ background: transparent; }}
QWidget#builderRight {{ background: transparent; }}
QWidget#heroPanel {{
    background: {glass};
    border: 1px solid {border_bright};
    border-radius: 18px;
}}
QLabel#heroTitle {{
    color: {p.text};
    font-size: 18pt;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#heroSubtitle {{ color: {p.muted_text}; font-size: 9pt; letter-spacing: 1px; }}
QLabel#heroModeBadge, QLabel#heroStatus {{
    background: {glass_soft};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 6px 11px;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#heroModeBadge {{ color: {p.accent}; }}
QLabel#heroStatus[state="ready"] {{ color: {p.muted_text}; }}
QLabel#heroStatus[state="data"] {{ color: {cyan}; border-color: {cyan}; }}
QLabel#heroStatus[state="fit"] {{ color: {p.accent}; border-color: {p.accent}; }}
QLabel#heroStatus[state="busy"] {{
    color: {selected_text};
    background: {p.accent};
    border-color: {p.accent_hover};
}}
QFrame#builderHero {{
    background: {glass};
    border: 1px solid {border_bright};
    border-radius: 17px;
}}
QLabel#builderTitle {{
    color: {p.text};
    font-size: 16pt;
    font-weight: 850;
    letter-spacing: 2px;
}}
QLabel#builderSubtitle, QLabel#builderHelp {{
    color: {p.muted_text};
    font-size: 9pt;
}}
QLabel#builderStatus {{
    background: {glass_soft};
    color: {p.accent};
    border: 1px solid {p.accent};
    border-radius: 12px;
    padding: 7px 11px;
    font-size: 8pt;
    font-weight: 750;
    letter-spacing: 1px;
}}
QLabel#builderStatus[state="empty"] {{
    color: {p.muted_text};
    border-color: {border};
}}
QLabel#builderFieldLabel {{
    color: {p.accent};
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#builderMicrocopy {{
    color: {p.muted_text};
    font-size: 8pt;
    font-weight: 650;
    letter-spacing: .6px;
}}
QLabel#builderSelectedLabel {{
    color: {cyan};
    font-weight: 700;
}}
QListWidget#elementPalette {{
    background: transparent;
    border: 0;
    padding: 2px;
}}
QListWidget#elementPalette::item {{
    background: {glass_soft};
    color: {p.text};
    border: 1px solid {border};
    border-radius: 13px;
    padding: 7px;
    margin: 3px;
    font-size: 8pt;
    font-weight: 700;
}}
QListWidget#elementPalette::item:hover {{
    background: {glass_hover};
    color: {p.accent};
    border-color: {border_bright};
}}
QListWidget#elementPalette::item:selected {{
    background: {p.accent};
    color: {selected_text};
    border-color: {p.accent_hover};
}}
QGraphicsView#schematicCanvas {{
    background: {p.plot_bg};
    border: 1px solid {border_bright};
    border-radius: 15px;
    padding: 1px;
}}
QGraphicsView#schematicCanvas:focus {{
    border: 1px solid {p.accent};
}}
QGraphicsView#schematicMinimap {{
    background: {p.plot_bg};
    border: 1px solid {border_bright};
    border-radius: 8px;
}}
QFrame#floatingEISMonitor {{
    background: {glass};
    border: 1px solid {p.accent};
    border-radius: 14px;
}}
QFrame#floatingEISMonitor[embedded="true"] {{
    background: transparent;
    border: 0;
    border-radius: 0;
}}
QFrame#floatingPlotHeader {{
    background: {glass_soft};
    border: 0;
    border-radius: 8px;
}}
QLabel#floatingPlotTitle {{
    color: {p.accent};
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#floatingPlotBadge, QLabel#floatingFrequencyLabel {{
    color: {cyan};
    font-size: 7pt;
    font-weight: 700;
}}
QPushButton#floatingPlotClose {{
    background: transparent;
    color: {p.muted_text};
    border: 0;
    padding: 0;
    font-size: 12pt;
}}
QPushButton#floatingPlotClose:hover {{ color: {p.negative}; }}
QListWidget#hypothesisList {{
    background: {input_glass};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 3px;
}}
QListWidget#hypothesisList::item {{
    color: {p.muted_text};
    padding: 4px 5px;
    border-bottom: 1px solid {border};
}}
QTreeWidget#topologyDropTree {{
    background: {input_glass};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 5px;
    alternate-background-color: {glass_soft};
}}
QTreeWidget#topologyDropTree::item {{
    min-height: 25px;
    border-radius: 7px;
    padding: 3px 5px;
}}
QTreeWidget#topologyDropTree::item:hover {{
    background: {glass_hover};
    color: {p.accent};
}}
QTreeWidget#topologyDropTree::item:selected {{
    background: {p.accent};
    color: {selected_text};
}}
QScrollArea#builderPreviewScroll {{
    background: {input_glass};
    border: 1px solid {border};
    border-radius: 12px;
}}
QWidget#builderPreview {{
    border-radius: 12px;
}}
QMenuBar {{
    background: {glass};
    color: {p.text};
    border-bottom: 1px solid {border};
    padding: 2px 6px;
}}
QMenuBar::item {{ padding: 5px 10px; border-radius: 7px; }}
QMenuBar::item:selected {{ background: {menu_selected}; }}
QMenu {{
    background: {p.panel};
    color: {p.text};
    border: 1px solid {border_bright};
    border-radius: 9px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.accent}; color: {selected_text}; }}
QToolBar#mainToolbar {{
    background: {glass_soft};
    color: {p.text};
    border: 0;
    border-bottom: 1px solid {border};
    spacing: 5px;
    padding: 5px 8px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px 10px;
    color: {p.text};
}}
QToolBar QToolButton:hover {{ background: {glass_hover}; border-color: {border}; }}
QToolBar QToolButton:checked {{ background: {p.accent}; color: {selected_text}; }}
QStatusBar {{
    background: {glass};
    color: {p.muted_text};
    border-top: 1px solid {border};
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 16px;
    margin-top: 15px;
    padding: 15px 10px 10px 10px;
    background: {glass};
    font-weight: 650;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 2px 8px;
    color: {p.accent};
    background: {group_title_bg};
    border-radius: 6px;
}}
QPushButton {{
    background: {glass_soft};
    color: {p.text};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 8px 13px;
    font-weight: 650;
}}
QPushButton:hover {{ background: {glass_hover}; border-color: {border_bright}; }}
QPushButton:pressed {{ background: {p.accent_pressed}; color: {selected_text}; }}
QPushButton#primaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {p.accent_pressed}, stop:0.52 {p.accent}, stop:1 {p.accent_hover});
    color: {selected_text};
    border: 1px solid {p.accent_hover};
    min-height: 18px;
}}
QPushButton#primaryButton:hover {{ border-color: {p.text}; }}
QPushButton#secondaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 rgba(23, 117, 125, 180), stop:1 rgba(101, 216, 222, 180));
    color: #F7FFFF;
    border-color: rgba(101, 216, 222, 150);
}}
QPushButton#quietButton {{ background: transparent; border-color: transparent; text-align: left; }}
QPushButton#quietButton:hover {{ background: {glass_soft}; border-color: {border}; }}
QPushButton#quietButton[compact="true"] {{
    padding: 5px 9px;
    text-align: center;
}}
QPushButton:disabled, QPushButton#primaryButton:disabled {{
    background: {disabled_bg};
    color: {disabled_text};
    border-color: {border};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget,
QPlainTextEdit, QListWidget, QAbstractSpinBox {{
    background: {input_glass};
    color: {p.text};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 5px;
    selection-background-color: {p.accent};
    selection-color: {selected_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTableWidget:focus {{ border: 1px solid {p.accent}; }}
QComboBox::drop-down {{ border: 0; width: 25px; }}
QComboBox QAbstractItemView {{
    background: {p.panel};
    color: {p.text};
    border: 1px solid {border_bright};
    selection-background-color: {p.accent};
    selection-color: {selected_text};
}}
QCheckBox {{ color: {p.text}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {border_bright};
    border-radius: 5px;
    background: {input_glass};
}}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent_hover}; }}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 14px;
    background: {glass};
    top: -1px;
}}
QTabBar::tab {{
    background: {glass_soft};
    color: {p.muted_text};
    padding: 9px 14px;
    margin: 0 3px 4px 0;
    border: 1px solid transparent;
    border-radius: 10px;
}}
QTabBar::tab:hover {{ background: {glass_hover}; color: {p.text}; border-color: {border}; }}
QTabBar::tab:selected {{
    background: {p.accent};
    color: {selected_text};
    border-color: {p.accent_hover};
    font-weight: 750;
}}
QTabWidget#builderRightTabs::pane {{
    border: 1px solid {border};
    border-radius: 12px;
    background: {glass_soft};
}}
QTabWidget#builderRightTabs QTabBar::tab {{
    min-width: 50px;
    padding: 7px 7px;
    margin-right: 2px;
    font-size: 8pt;
    letter-spacing: .5px;
}}
QTabWidget#builderRightTabs QGroupBox {{
    margin-top: 0;
    padding: 8px;
    border: 0;
    border-radius: 0;
    background: transparent;
}}
QHeaderView::section {{
    background: {glass_soft};
    color: {p.text};
    padding: 7px;
    border: 0;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-weight: 650;
}}
QTableCornerButton::section {{ background: {glass_soft}; border: 1px solid {border}; }}
QTableWidget {{ gridline-color: {border}; alternate-background-color: {glass_soft}; }}
QProgressBar {{
    border: 1px solid {border};
    border-radius: 7px;
    text-align: center;
    background: {input_glass};
    color: {p.text};
    min-height: 13px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {p.accent_pressed}, stop:0.55 {p.accent}, stop:1 {cyan});
    border-radius: 6px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: {scrollbar_bg}; width: 11px; margin: 1px; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background: {scrollbar_handle}; min-height: 34px; border-radius: 5px; }}
QScrollBar:horizontal {{ background: {scrollbar_bg}; height: 11px; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background: {scrollbar_handle}; min-width: 34px; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter#workspaceSplitter::handle {{ background: {border}; width: 1px; margin: 12px 5px; }}
QLabel {{ color: {p.text}; background: transparent; }}
QLabel#helpText {{ color: {p.muted_text}; font-size: 9pt; }}
QLabel#fileSummary {{
    color: {p.muted_text};
    background: {input_glass};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 9px;
}}
QLabel#emptyState {{
    color: {p.muted_text};
    background: {glass_soft};
    border: 1px dashed {border_bright};
    border-radius: 14px;
    padding: 20px;
    font-size: 11pt;
}}
QToolTip {{ background: {tooltip_bg}; color: {p.text}; border: 1px solid {p.accent}; padding: 6px; }}
QMessageBox, QDialog {{ background: {p.window}; }}
"""


# Backward-compatible names used by earlier project versions.
GOLD_STYLE = get_stylesheet("light")
DARK_GOLD_STYLE = get_stylesheet("dark")
