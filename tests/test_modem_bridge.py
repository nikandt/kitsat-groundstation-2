"""
Unit tests for ModemBridge.

These tests mock the kitsat Modem so no hardware is required.
"""

from unittest.mock import MagicMock, patch
import pytest

from kitsat_gs.core.modem_bridge import ModemBridge


@pytest.fixture
def bridge(qtbot):
    b = ModemBridge()
    yield b
    if b.is_connected:
        b.disconnect()


def test_initial_state(bridge):
    assert not bridge.is_connected


def test_connect_port_success(bridge, qtbot):
    with patch("kitsat_gs.core.modem_bridge.Modem") as MockModem:
        instance = MockModem.return_value
        instance.connect.return_value = 1
        instance.is_connected = True
        instance.port = "COM3"
        instance.read.return_value = None

        with qtbot.waitSignal(bridge.connected, timeout=2000) as blocker:
            bridge.connect_port("COM3")

        assert blocker.args == ["COM3"]


def test_connect_port_failure(bridge, qtbot):
    with patch("kitsat_gs.core.modem_bridge.Modem") as MockModem:
        instance = MockModem.return_value
        instance.connect.return_value = 0
        instance.is_connected = False

        with qtbot.waitSignal(bridge.error, timeout=2000) as blocker:
            bridge.connect_port("COM99")

        assert "COM99" in blocker.args[0]


def test_send_command_when_disconnected(bridge, qtbot):
    with qtbot.waitSignal(bridge.error, timeout=2000) as blocker:
        bridge.send_command("ping")

    assert "Not connected" in blocker.args[0]
