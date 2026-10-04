"""Application pages (dashboard, scan, results, settings, history)."""

from .compare_dialog import CompareDialog
from .dashboard_page import DashboardPage
from .history_page import HistoryPage
from .results_page import ResultsPage
from .scan_page import ScanPage
from .settings_page import SettingsPage

__all__ = [
    "CompareDialog",
    "DashboardPage",
    "HistoryPage",
    "ResultsPage",
    "ScanPage",
    "SettingsPage",
]
