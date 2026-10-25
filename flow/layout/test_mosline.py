"""A netlist's MOS widths in both PDK conventions (``flow/layout/stems/mosline.py``), without a PDK."""

from __future__ import annotations

import pytest

from flow.layout.stems import mosline

# the same device, 8 fingers of 500 nm, as each convention writes it
TOTAL = "Mpair d g s b nch w=4000n l=180n nf=8 m=1"
PER_FINGER = "Mpair d g s b nch w=500n l=180n nf=8 m=1"
BY_M = "Mpair d g s b nch w=500n l=180n m=8"  # fingers by m: w per finger in either convention


def test_finger_width_reads_w_by_the_convention() -> None:
    assert mosline.finger_width(mosline.params(TOTAL.split()), w_per_finger=False) == 500
    assert mosline.finger_width(mosline.params(PER_FINGER.split()), w_per_finger=True) == 500
    # read in the other convention, the same line is a different device: what the flag is for
    assert mosline.finger_width(mosline.params(PER_FINGER.split()), w_per_finger=False) == 62


@pytest.mark.parametrize(("line", "per"), [(TOTAL, False), (PER_FINGER, True), (BY_M, False), (BY_M, True)])
def test_per_finger_gives_one_fingers_width_and_all_fingers(line: str, per: bool) -> None:
    out = mosline.per_finger(line, w_per_finger=per).split()
    p = mosline.params(out)
    assert (p["w"], p["nf"], p["m"]) == ("500n", "8", "1")


def test_per_finger_keeps_ng() -> None:
    p = mosline.params(mosline.per_finger("Mx d g s b nch w=4u l=180n ng=8", w_per_finger=False).split())
    assert (p["w"], p["ng"], p["m"]) == ("500n", "8", "1") and "nf" not in p


def test_split_shares_fingers_and_total_width() -> None:
    a, b = mosline.split(TOTAL, {"Mpair": 2}, w_per_finger=False).split("\n")[:2]
    assert a.split()[0] == "Mpair_a" and b.split()[0] == "Mpair_b"
    assert mosline.params(a.split()) == {"w": "2000n", "l": "180n", "nf": "4", "m": "1"}


def test_split_keeps_a_per_finger_width() -> None:
    a = mosline.split(PER_FINGER, {"Mpair": 2}, w_per_finger=True).split("\n")[0]
    assert mosline.params(a.split()) == {"w": "500n", "l": "180n", "nf": "4", "m": "1"}
    # a per-finger width need not divide by the parts
    odd = mosline.split("Mx d g s b nch w=501n l=180n nf=8", {"Mx": 2}, w_per_finger=True)
    assert mosline.params(odd.split("\n")[0].split())["w"] == "501n"
    with pytest.raises(ValueError, match="do not split"):
        mosline.split("Mx d g s b nch w=4001n l=180n nf=8", {"Mx": 2}, w_per_finger=False)


def test_split_then_per_finger_agree_in_both_conventions() -> None:
    for line, per in ((TOTAL, False), (PER_FINGER, True)):
        out = mosline.per_finger(mosline.split(line, {"Mpair": 2}, w_per_finger=per), w_per_finger=per)
        parts = [mosline.params(f.split()) for f in out.splitlines() if f]
        assert [(p["w"], p["nf"]) for p in parts] == [("500n", "4"), ("500n", "4")]


def test_w_per_finger_is_read_from_the_pdk_logic_source(tmp_path) -> None:
    for name, source, expected in (
        ("per", "import hdl21  # never imported here\nMOS_W_PER_FINGER = True\n", True),
        ("total", "import hdl21\nMOS_FINGER_UNITS = {'analog': 9}\n", False),
    ):
        (tmp_path / name / "hdl21").mkdir(parents=True)
        (tmp_path / name / "hdl21" / "pdk_logic.py").write_text(source)
        assert mosline.w_per_finger(tmp_path / name) is expected
    assert mosline.w_per_finger(tmp_path / "none") is False  # no pdk_logic: total width
