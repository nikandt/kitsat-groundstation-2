"""
Tests for ImageManager — uses a temporary directory to simulate
kitsat's data/files structure without needing the actual package.
"""

import time
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from kitsat_gs.core.image_manager import ImageManager, ImageRecord, _find_kitsat_data_root


@pytest.fixture
def tmp_data(tmp_path):
    """Create a fake kitsat data/files directory."""
    data_root = tmp_path / "data" / "files"
    data_root.mkdir(parents=True)
    return data_root


@pytest.fixture
def manager(qapp, tmp_data):
    with patch("kitsat_gs.core.image_manager._find_kitsat_data_root", return_value=tmp_data):
        mgr = ImageManager()
        yield mgr
        mgr._poll_timer.stop()


def _make_jpeg(path: Path) -> None:
    """Write a minimal valid JPEG to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal JPEG: SOI + EOI
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10 + b"\xff\xd9")


def test_detects_new_downloaded_image(manager, tmp_data, qtbot):
    session = tmp_data / "2024_01_01_120000" / "downloaded"
    jpeg = session / "image-0.jpeg"

    with qtbot.waitSignal(manager.image_received, timeout=5000) as blocker:
        _make_jpeg(jpeg)
        manager._scan()  # trigger immediately

    record = blocker.args[0]
    assert isinstance(record, ImageRecord)
    assert record.source == "downloaded"
    assert record.session == "2024_01_01_120000"
    assert record.path == jpeg


def test_detects_streamed_image(manager, tmp_data, qtbot):
    session = tmp_data / "2024_01_01_130000" / "streamed"
    jpeg = session / "image-0.jpeg"

    with qtbot.waitSignal(manager.image_received, timeout=5000) as blocker:
        _make_jpeg(jpeg)
        manager._scan()

    record = blocker.args[0]
    assert record.source == "streamed"


def test_no_duplicate_signals(manager, tmp_data, qtbot):
    session = tmp_data / "2024_01_01_140000" / "downloaded"
    jpeg = session / "image-0.jpeg"
    _make_jpeg(jpeg)
    manager._scan()

    received = []
    manager.image_received.connect(lambda r: received.append(r))
    manager._scan()
    manager._scan()

    assert len(received) == 0   # already known, should not fire again


def test_all_images_lists_known_images(manager, tmp_data):
    for i in range(3):
        _make_jpeg(tmp_data / "sess1" / "downloaded" / f"image-{i}.jpeg")
    manager._scan()

    images = manager.all_images()
    assert len(images) == 3
    assert all(isinstance(r, ImageRecord) for r in images)


def test_session_started_signal(manager, tmp_data, qtbot):
    session_dir = tmp_data / "2024_02_01_000000"
    (session_dir / "downloaded").mkdir(parents=True)

    with qtbot.waitSignal(manager.session_started, timeout=5000) as blocker:
        manager._scan()

    assert blocker.args[0] == "2024_02_01_000000"
