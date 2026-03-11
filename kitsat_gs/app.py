import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from loguru import logger
from pathlib import Path

from kitsat_gs.ui.main_window import MainWindow


def _setup_logging() -> None:
    log_dir = Path.home() / "Documents" / "Kitsat" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "kitsat-gs.log",
        rotation="2 MB",
        retention=5,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
    )
    logger.info("Kitsat GS v2 starting up")


def main() -> int:
    _setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Kitsat GS")
    app.setOrganizationName("Arctic Astronautics")
    app.setApplicationVersion("2.0.0")

    # Load dark theme stylesheet
    qss_path = Path(__file__).parent / "assets" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text())

    window = MainWindow()
    window.show()

    return app.exec()
