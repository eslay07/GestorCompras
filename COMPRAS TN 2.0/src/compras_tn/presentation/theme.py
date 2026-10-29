STYLE = """
QWidget { color: #1f2937; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QDialog, QStackedWidget, QScrollArea { background: #f4f7fb; }
QLabel { background: transparent; }
#Sidebar, #Sidebar QWidget, #Sidebar QScrollArea { background: #172236; }
#Sidebar { min-width: 220px; max-width: 220px; }
#Brand { color: white; font-size: 17px; font-weight: 700; padding: 18px 14px 8px 14px; }
#UserLabel { color: #a9bad1; padding: 0 14px 14px 14px; }
#SectionLabel { color: #7f93ad; font-size: 9px; font-weight: 700; padding: 14px 14px 4px 14px; }
QPushButton#NavButton { color: #cbd5e1; background: transparent; border: 0; text-align: left; padding: 9px 16px; }
QPushButton#NavButton:hover { background: #253651; color: white; }
QPushButton#NavButton:checked { background: #2563eb; color: white; font-weight: 600; }
QPushButton { background: #2563eb; color: white; border: 0; border-radius: 5px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #9ca3af; }
QPushButton[secondary="true"] { background: #e5e7eb; color: #374151; }
QPushButton[danger="true"] { background: #dc2626; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QDateTimeEdit {
    background: white; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
QTableView, QTableWidget { background: white; alternate-background-color: #f8fafc; border: 1px solid #dbe3ee; gridline-color: #edf2f7; }
QHeaderView::section { background: #e9eff8; color: #243247; border: 0; border-right: 1px solid #d4deea; padding: 7px; font-weight: 600; }
QGroupBox { background: white; border: 1px solid #dbe3ee; border-radius: 7px; margin-top: 12px; padding: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
#LoginCard, #InfoCard { background: white; border: 1px solid #dbe3ee; border-radius: 9px; padding: 12px; }
QTabWidget::pane { border: 1px solid #dbe3ee; background: white; }
QTabBar::tab { background: #e5eaf1; padding: 9px 16px; }
QTabBar::tab:selected { background: #2563eb; color: white; }
QProgressBar { border: 1px solid #cbd5e1; background: white; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #2563eb; }
#PageTitle { font-size: 22px; font-weight: 700; color: #172236; }
#PageSubtitle { color: #64748b; }
#StatusSuccess { color: #047857; font-weight: 600; }
#StatusError { color: #b91c1c; font-weight: 600; }
"""
