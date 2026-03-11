"""
Tests for ScriptEngine — no hardware or Qt required.
"""

import pytest
from kitsat_gs.core.script_engine import ScriptEngine, ScriptCommand, ScriptError

COMMANDS = ["ping", "beep", "reset", "cam_take_pic", "imu_get_all"]


def run_all(code: str) -> list[ScriptCommand]:
    """Run a script to completion and return all commands."""
    engine = ScriptEngine(code, COMMANDS)
    return list(engine)


# ------------------------------------------------------------------
# Basic commands
# ------------------------------------------------------------------

def test_single_satellite_command():
    cmds = run_all("ping")
    assert len(cmds) == 1
    assert cmds[0].kind == "satellite"
    assert cmds[0].line == "ping"


def test_multiple_commands():
    cmds = run_all("ping\nreset\ncam_take_pic")
    kinds = [c.kind for c in cmds]
    assert kinds.count("satellite") == 3


def test_wait_command():
    cmds = run_all("wait 2")
    assert cmds[0].kind == "wait"
    assert cmds[0].value_s == 2.0


def test_wait_ms_command():
    cmds = run_all("wait_ms 500")
    assert cmds[0].kind == "wait_ms"
    assert abs(cmds[0].value_s - 0.5) < 1e-6


# ------------------------------------------------------------------
# Variables
# ------------------------------------------------------------------

def test_variable_declaration():
    engine = ScriptEngine("var x = 5", COMMANDS)
    list(engine)
    assert engine.get_variable("x") == "5"


def test_assignment():
    engine = ScriptEngine("var x = 0\nx = 7", COMMANDS)
    cmds = list(engine)
    assert engine.get_variable("x") == "7"
    assert any(c.kind == "assignment" for c in cmds)


def test_variable_in_command():
    engine = ScriptEngine("var n = 3\nbeep n", COMMANDS)
    cmds = [c for c in engine if c.kind == "satellite"]
    assert cmds[0].line == "beep 3"


# ------------------------------------------------------------------
# Control flow
# ------------------------------------------------------------------

def test_for_loop():
    code = "var i = 0\nfor i < 3 {\n    ping\n}"
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 3


def test_for_loop_zero_iterations():
    code = "var i = 5\nfor i < 3 {\n    ping\n}"
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 0


def test_if_true_branch():
    code = "var x = 1\nif x == 1 {\n    ping\n}"
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 1


def test_if_false_branch():
    code = "var x = 0\nif x == 1 {\n    ping\n}"
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 0


def test_if_else():
    code = "var x = 0\nif x == 1 {\n    ping\n}else {\n    reset\n}"
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 1
    assert cmds[0].line == "reset"


# ------------------------------------------------------------------
# Functions
# ------------------------------------------------------------------

def test_function_definition_and_call():
    code = (
        "Function greet() {\n"
        "    ping\n"
        "    beep 1\n"
        "}\n"
        "greet()\n"
    )
    cmds = [c for c in run_all(code) if c.kind == "satellite"]
    assert len(cmds) == 2
    assert cmds[0].line == "ping"
    assert cmds[1].line == "beep 1"


# ------------------------------------------------------------------
# UI commands
# ------------------------------------------------------------------

def test_image_frame_command():
    cmds = run_all("ImageFrame")
    assert cmds[0].kind == "ui"
    assert "ImageFrame" in cmds[0].line


# ------------------------------------------------------------------
# Empty / edge cases
# ------------------------------------------------------------------

def test_empty_script():
    assert run_all("") == []


def test_comments_and_blank_lines():
    # Blank lines should be ignored
    cmds = run_all("\n\n\nping\n\n")
    assert len([c for c in cmds if c.kind == "satellite"]) == 1
