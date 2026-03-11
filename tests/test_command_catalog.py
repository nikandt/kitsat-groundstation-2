from kitsat_gs.core import command_catalog


def test_load_returns_commands():
    cmds = command_catalog.load()
    assert len(cmds) > 0


def test_known_command_lookup():
    cmd = command_catalog.get("ping")
    assert cmd is not None
    assert cmd.target_id == 1
    assert cmd.command_id == 5
    assert cmd.param_type == ""


def test_beep_has_int_param():
    cmd = command_catalog.get("beep")
    assert cmd is not None
    assert cmd.param_type == "int"


def test_cam_get_blocks_has_int_int_param():
    cmd = command_catalog.get("cam_get_blocks")
    assert cmd is not None
    assert cmd.param_type == "int|int"


def test_unknown_command_returns_none():
    assert command_catalog.get("does_not_exist") is None


def test_by_target_returns_correct_subsystem():
    buzzer_cmds = command_catalog.by_target(7)
    names = [c.name for c in buzzer_cmds]
    assert "beep" in names
    assert "morse" in names


def test_all_names_is_list_of_strings():
    names = command_catalog.all_names()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
