"""
bitcoin_terminal/gui/theme.py

SATURN visual design system.
Palette: deep slate + amber/gold + electric cyan + crimson alerts.
Typography: JetBrains Mono (monospace data), Rajdhani (display headers).
"""

# ── Colour tokens ─────────────────────────────────────────────────────────────

class C:
    # Backgrounds
    BASE        = "#080B10"
    SURFACE     = "#0D1117"
    PANEL       = "#111823"
    PANEL_ALT   = "#131C28"
    BORDER      = "#1E2D40"
    BORDER_LT   = "#253548"

    # Primary accent — amber / gold
    AMBER       = "#F5A623"
    AMBER_DIM   = "#A06A10"
    AMBER_GLOW  = "#FFD580"

    # Secondary accent — electric cyan
    CYAN        = "#00D4FF"
    CYAN_DIM    = "#007B99"

    # Semantic
    GREEN       = "#00E676"
    GREEN_DIM   = "#00A152"
    RED         = "#FF3D57"
    RED_DIM     = "#C0002A"
    YELLOW      = "#FFD600"
    PURPLE      = "#BB86FC"

    # Text
    TEXT_PRI    = "#E8EDF2"
    TEXT_SEC    = "#7A8FA6"
    TEXT_MUT    = "#3D5168"
    TEXT_INV    = "#080B10"

    # Severity
    INFO_BG     = "#0D2235"
    WARN_BG     = "#2A1E00"
    CRIT_BG     = "#280010"


def build_stylesheet() -> str:
    c = C
    return f"""
/* ── Reset ──────────────────────────────────────────────────────────────── */
* {{
    font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", monospace;
    color: {c.TEXT_PRI};
    selection-background-color: {c.AMBER_DIM};
    selection-color: {c.AMBER_GLOW};
}}

QMainWindow, QWidget {{
    background-color: {c.BASE};
}}

/* ── Tab bar ─────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {c.BORDER};
    background: {c.SURFACE};
    border-radius: 0px;
}}
QTabBar {{
    background: {c.BASE};
}}
QTabBar::tab {{
    background: {c.BASE};
    color: {c.TEXT_SEC};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 22px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    min-width: 120px;
}}
QTabBar::tab:selected {{
    color: {c.AMBER};
    border-bottom: 2px solid {c.AMBER};
    background: {c.SURFACE};
}}
QTabBar::tab:hover:!selected {{
    color: {c.TEXT_PRI};
    background: {c.PANEL};
}}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {c.SURFACE};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {c.BORDER_LT};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.AMBER_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {c.SURFACE};
    height: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {c.BORDER_LT};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c.AMBER_DIM};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Labels ──────────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    font-size: 12px;
}}
QLabel#stat_value {{
    font-size: 22px;
    font-weight: 700;
    color: {c.AMBER};
}}
QLabel#stat_label {{
    font-size: 10px;
    letter-spacing: 1.5px;
    color: {c.TEXT_SEC};
    text-transform: uppercase;
}}
QLabel#section_header {{
    font-size: 11px;
    letter-spacing: 2px;
    color: {c.AMBER};
    font-weight: 700;
    text-transform: uppercase;
    border-bottom: 1px solid {c.BORDER};
    padding-bottom: 4px;
}}
QLabel#price_display {{
    font-size: 36px;
    font-weight: 700;
    color: {c.AMBER_GLOW};
    letter-spacing: -1px;
}}
QLabel#ticker_positive {{
    color: {c.GREEN};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#ticker_negative {{
    color: {c.RED};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#alert_badge {{
    background: {c.RED};
    color: {c.TEXT_PRI};
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 700;
}}

/* ── Metric cards ────────────────────────────────────────────────────────── */
QFrame#metric_card {{
    background: {c.PANEL};
    border: 1px solid {c.BORDER};
    border-radius: 4px;
}}
QFrame#metric_card_accent {{
    background: {c.PANEL};
    border: 1px solid {c.AMBER_DIM};
    border-radius: 4px;
    border-left: 3px solid {c.AMBER};
}}
QFrame#metric_card_cyan {{
    background: {c.PANEL};
    border: 1px solid {c.CYAN_DIM};
    border-radius: 4px;
    border-left: 3px solid {c.CYAN};
}}
QFrame#metric_card_green {{
    background: {c.PANEL};
    border: 1px solid {c.GREEN_DIM};
    border-radius: 4px;
    border-left: 3px solid {c.GREEN};
}}
QFrame#metric_card_red {{
    background: {c.PANEL};
    border: 1px solid {c.RED_DIM};
    border-radius: 4px;
    border-left: 3px solid {c.RED};
}}

/* ── Tables ──────────────────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background: {c.SURFACE};
    alternate-background-color: {c.PANEL};
    gridline-color: {c.BORDER};
    border: 1px solid {c.BORDER};
    font-size: 11px;
    selection-background-color: {c.AMBER_DIM};
    selection-color: {c.AMBER_GLOW};
}}
QHeaderView::section {{
    background: {c.PANEL};
    color: {c.TEXT_SEC};
    border: none;
    border-bottom: 1px solid {c.BORDER};
    border-right: 1px solid {c.BORDER};
    padding: 6px 10px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}

/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c.PANEL};
    border: 1px solid {c.BORDER};
    border-radius: 3px;
    padding: 7px 12px;
    font-size: 12px;
    color: {c.TEXT_PRI};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {c.AMBER};
}}
QLineEdit#search_input {{
    background: {c.PANEL_ALT};
    border: 1px solid {c.BORDER_LT};
    border-radius: 3px;
    padding: 8px 14px;
    font-size: 13px;
    color: {c.TEXT_PRI};
    min-height: 36px;
}}
QLineEdit#search_input:focus {{
    border: 1px solid {c.AMBER};
    background: {c.PANEL};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {c.PANEL};
    border: 1px solid {c.BORDER};
    selection-background-color: {c.AMBER_DIM};
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background: {c.PANEL};
    border: 1px solid {c.BORDER};
    border-radius: 3px;
    padding: 7px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    color: {c.TEXT_PRI};
}}
QPushButton:hover {{
    background: {c.PANEL_ALT};
    border: 1px solid {c.BORDER_LT};
    color: {c.AMBER};
}}
QPushButton:pressed {{
    background: {c.AMBER_DIM};
    color: {c.AMBER_GLOW};
}}
QPushButton#btn_primary {{
    background: {c.AMBER_DIM};
    border: 1px solid {c.AMBER};
    color: {c.AMBER_GLOW};
    font-weight: 700;
    letter-spacing: 1.5px;
}}
QPushButton#btn_primary:hover {{
    background: {c.AMBER};
    color: {c.TEXT_INV};
}}
QPushButton#btn_danger {{
    background: {c.RED_DIM};
    border: 1px solid {c.RED};
    color: {c.RED};
}}
QPushButton#btn_danger:hover {{
    background: {c.RED};
    color: #fff;
}}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {c.PANEL};
    border-top: 1px solid {c.BORDER};
    font-size: 10px;
    letter-spacing: 0.5px;
    color: {c.TEXT_SEC};
    padding: 3px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── Splitter ────────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {c.BORDER};
}}
QSplitter::handle:hover {{
    background: {c.AMBER_DIM};
}}

/* ── ToolTip ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background: {c.PANEL};
    border: 1px solid {c.AMBER_DIM};
    color: {c.TEXT_PRI};
    padding: 4px 8px;
    font-size: 11px;
    border-radius: 3px;
}}

/* ── Progress bars ───────────────────────────────────────────────────────── */
QProgressBar {{
    background: {c.BORDER};
    border: none;
    border-radius: 2px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {c.AMBER};
    border-radius: 2px;
}}
QProgressBar#bar_green::chunk {{
    background: {c.GREEN};
}}
QProgressBar#bar_cyan::chunk {{
    background: {c.CYAN};
}}
QProgressBar#bar_red::chunk {{
    background: {c.RED};
}}

/* ── List views ──────────────────────────────────────────────────────────── */
QListWidget {{
    background: {c.SURFACE};
    border: 1px solid {c.BORDER};
    font-size: 11px;
}}
QListWidget::item {{
    padding: 5px 10px;
    border-bottom: 1px solid {c.BORDER};
}}
QListWidget::item:selected {{
    background: {c.AMBER_DIM};
    color: {c.AMBER_GLOW};
}}
QListWidget::item:hover {{
    background: {c.PANEL};
}}

/* ── CheckBox ────────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 11px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {c.BORDER};
    background: {c.PANEL};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {c.AMBER};
    border: 1px solid {c.AMBER};
}}

/* ── GroupBox ────────────────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {c.BORDER};
    border-radius: 4px;
    margin-top: 14px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: {c.TEXT_SEC};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    background: {c.BASE};
    color: {c.TEXT_SEC};
}}
"""


def severity_color(severity: str) -> str:
    return {
        "INFO":     C.CYAN,
        "WARNING":  C.YELLOW,
        "CRITICAL": C.RED,
    }.get(severity, C.TEXT_PRI)


def severity_bg(severity: str) -> str:
    return {
        "INFO":     C.INFO_BG,
        "WARNING":  C.WARN_BG,
        "CRITICAL": C.CRIT_BG,
    }.get(severity, C.PANEL)
