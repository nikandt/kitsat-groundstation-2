from kitsat_gs.core import housekeeping_catalog


def test_load_returns_definitions():
    defs = housekeeping_catalog.load()
    assert len(defs) > 0


def test_magnetometer_has_three_subvalues():
    defs = housekeeping_catalog.load()
    mag = next(d for d in defs if d.subtype == "Magnetometer")
    assert mag.subvalues == ["x", "y", "z"]
    assert mag.units == "Gs"


def test_acceleration_conversion():
    defs = housekeeping_catalog.load()
    acc = next(d for d in defs if d.subtype == "Acceleration")
    converted = acc.convert([1.0, 1.0, 1.0])
    assert all(abs(v - 9.81) < 1e-6 for v in converted)


def test_velocity_conversion_factor():
    defs = housekeeping_catalog.load()
    vel = next(d for d in defs if d.subtype == "Velocity")
    converted = vel.convert([1.0])
    assert abs(converted[0] - 0.514444) < 1e-6


def test_by_command_lookup():
    hk = housekeeping_catalog.by_command(5, 1)  # IMU magnetometer
    assert hk is not None
    assert hk.subtype == "Magnetometer"


def test_by_command_missing_returns_none():
    assert housekeeping_catalog.by_command(99, 99) is None


def test_full_name():
    defs = housekeeping_catalog.load()
    mag = next(d for d in defs if d.subtype == "Magnetometer")
    assert mag.full_name == "Attitude / Magnetometer"
