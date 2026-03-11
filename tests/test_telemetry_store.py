import time
import pytest
from kitsat_gs.core.telemetry_store import TelemetryStore


@pytest.fixture
def store(qapp):
    return TelemetryStore(max_samples=10)


def test_record_and_latest(store):
    store.record("test/channel", 42.0)
    sample = store.latest("test/channel")
    assert sample is not None
    assert sample.value == 42.0


def test_series_returns_all_samples(store):
    for i in range(5):
        store.record("test/series", float(i))
    series = store.series("test/series")
    assert len(series) == 5
    assert [s.value for s in series] == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_max_samples_ring_buffer(store):
    for i in range(15):
        store.record("test/ring", float(i))
    series = store.series("test/ring")
    assert len(series) == 10  # capped at max_samples
    assert series[-1].value == 14.0


def test_keys(store):
    store.record("a/b", 1.0)
    store.record("c/d", 2.0)
    assert set(store.keys()) == {"a/b", "c/d"}


def test_clear(store):
    store.record("x/y", 1.0)
    store.clear()
    assert store.keys() == []
    assert store.latest("x/y") is None


def test_record_packet_multi_channel(store, qtbot):
    with qtbot.waitSignals([store.updated, store.updated, store.updated], timeout=1000):
        store.record_packet("Attitude", "Magnetometer", ["x", "y", "z"], [1.0, 2.0, 3.0])

    assert store.latest("Attitude/Magnetometer/x").value == 1.0
    assert store.latest("Attitude/Magnetometer/y").value == 2.0
    assert store.latest("Attitude/Magnetometer/z").value == 3.0
