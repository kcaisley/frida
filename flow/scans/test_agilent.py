"""Safely probe the Agilent 33250A RS-232 connection with ``*IDN?`` only.

This does not configure or enable the waveform-generator output.
"""

import argparse
from pathlib import Path

import serial

DEFAULT_PORT = "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT, help="serial device path")
    parser.add_argument("--baudrate", type=int, default=57600, help="baud rate selected on the 33250A")
    parser.add_argument("--timeout", type=float, default=2.0, help="reply timeout in seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    port_path = Path(args.port)
    if not port_path.exists():
        raise SystemExit(f"Serial device does not exist: {port_path}")

    print(f"Opening {port_path} -> {port_path.resolve()}")
    try:
        with serial.Serial(
            port=args.port,
            baudrate=args.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=args.timeout,
            write_timeout=args.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        ) as agilent:
            # Linux does not implement automatic DSR/DTR flow control, but it
            # can drive these outputs. A full-handshake null-modem cable must
            # cross PC DTR to the 33250A DSR input (and PC RTS to instrument CTS).
            agilent.dtr = True
            agilent.rts = True
            agilent.reset_input_buffer()

            print(f"Serial settings: {agilent.baudrate} baud, 8N1")
            print(
                "Modem lines: "
                f"PC outputs DTR={agilent.dtr}, RTS={agilent.rts}; "
                f"PC inputs DSR={agilent.dsr}, CTS={agilent.cts}, "
                f"DCD={agilent.cd}, RI={agilent.ri}"
            )

            agilent.write(b"*IDN?\n")
            agilent.flush()
            reply = agilent.readline()
    except (OSError, serial.SerialException) as error:
        raise SystemExit(f"Could not use serial device {port_path}: {error}") from error

    if not reply:
        raise SystemExit(
            "No reply to *IDN?. On the 33250A front panel, select RS-232 rather than the factory-default GPIB, "
            f"then match {args.baudrate} baud, parity None (8 data bits), and 1 stop bit. If handshake is DTR/DSR, "
            "use a full-handshake null-modem cable wired TX↔RX, DTR↔DSR, RTS↔CTS, and GND↔GND. "
            "For a three-wire cable, select handshake None and a baud rate below 9600 on the instrument, then pass "
            "the same rate with --baudrate (for example, 4800)."
        )

    print(f"Raw reply: {reply!r}")
    print(f"Instrument: {reply.decode('ascii', errors='replace').strip()}")


if __name__ == "__main__":
    main()
