import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from loguru import logger

from kitsat_gs.config import settings
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


def load_stylesheet(theme: str) -> str:
    assets = Path(__file__).parent / "assets"
    if theme == "light":
        qss_path = assets / "style_light.qss"
    else:
        qss_path = assets / "style.qss"
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    return ""


def main() -> int:
    _setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Kitsat GS")
    app.setOrganizationName("Arctic Astronautics")
    app.setApplicationVersion("2.0.0")

    app.setStyleSheet(load_stylesheet(settings.theme()))

    window = MainWindow(app)
    window.show()

    return app.exec()
