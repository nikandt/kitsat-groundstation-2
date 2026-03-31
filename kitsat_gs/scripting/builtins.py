"""Built-in DSL keyword documentation and REPL help."""

BUILTIN_DOCS = {
    "SEND": (
        "SEND <COMMAND>",
        "Send a command to the satellite.\n"
        "Example: SEND PING",
    ),
    "WAIT": (
        "WAIT <seconds>",
        "Pause execution for the given number of seconds.\n"
        "Example: WAIT 2.5",
    ),
    "GET": (
        "GET TELEMETRY <field>",
        "Read a telemetry field value.\n"
        "Fields: battery_percent, temp_obc, temp_battery, latitude, "
        "longitude, altitude_km, mode, rssi_dbm, ...\n"
        "Example: GET TELEMETRY battery_percent",
    ),
    "SET": (
        "SET MODE <mode>",
        "Set satellite operating mode.\n"
        "Modes: nominal, low_power, safe, science, detumble\n"
        "Example: SET MODE low_power",
    ),
    "LOG": (
        'LOG "message"',
        "Print a message to the script output.\n"
        'Example: LOG "Science sequence starting"',
    ),
    "REPEAT": (
        "REPEAT <n>:\n    ...\nEND",
        "Execute a block of statements n times.\n"
        "Example:\n  REPEAT 3:\n      SEND BEACON\n      WAIT 5.0\n  END",
    ),
    "IF": (
        "IF <field> <op> <value>:\n    ...\nEND",
        "Conditionally execute a block based on a telemetry comparison.\n"
        "Operators: > < >= <= == !=\n"
        "Example:\n  IF battery_percent > 20:\n      SEND CAPTURE_IMAGE\n  END",
    ),
    "END": (
        "END",
        "Terminates a REPEAT or IF block.",
    ),
}

EXAMPLE_SCRIPT = """\
# Kitsat Example Script
LOG "Starting science sequence"
SEND PING
WAIT 2.0
GET TELEMETRY battery_percent
IF battery_percent > 20:
    SEND CAPTURE_IMAGE
    WAIT 1.0
    LOG "Image captured"
END
REPEAT 3:
    SEND BEACON
    WAIT 5.0
END
SET MODE low_power
LOG "Sequence complete"
"""


def help_text() -> str:
    lines = ["Kitsat DSL Built-in Commands", "=" * 40, ""]
    for kw, (syntax, desc) in BUILTIN_DOCS.items():
        lines.append(f"  {syntax}")
        for line in desc.split("\n"):
            lines.append(f"    {line}")
        lines.append("")
    return "\n".join(lines)
