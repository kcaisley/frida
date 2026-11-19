"""The sizing of a bootstrapped switch (``params._bootstrapped``) and the designs ``params.valid``
admits: each expected value worked by hand from the unit capacitances (``GATE_F`` 86 aF a unit area,
``OVERLAP_F`` 36 aF and ``JUNCTION_F`` 30 aF a unit width, ``BOTTOM_F`` 8.6 aF a unit area) and
[Razavi-ADC] Eq. (3.69), p. 49 and Eq. (3.70), p. 50."""

import pytest

from flow.sweep.runner import design_space

from . import runs
from .params import (
    BOOST_MIN,
    LOAD_F,
    Params,
    SwitchType,
    _boost_f,
    _boosted_f,
    _bootstrapped,
    _bottom_f,
    _bottom_length,
    _gate_f,
    valid,
)

AF = 1e-18


def test_a_gate_is_its_area_and_its_two_overlaps() -> None:
    """[Razavi-ADC] Eq. (3.69), p. 49: C_G = (W L) C_ox + 2 W C_ov. 32 by 1 units:
    32 x (1 x 86 + 2 x 36) = 5056 aF; 4 by 14: 4 x (14 x 86 + 72) = 5104 aF."""
    assert _gate_f(32, 1) == pytest.approx(5056 * AF)
    assert _gate_f(4, 14) == pytest.approx(5104 * AF)
    assert _gate_f(32, 1, gate_f=100 * AF, overlap_f=0.0) == pytest.approx(3200 * AF)


def test_the_32_unit_bootstrap_by_hand() -> None:
    """The 32 by 1 switch, helpers 4 units, into 1 pF. With Mbot_in 14 long the boosted nodes
    carry C_G1 = 5056 aF, C_G2 = 5104 aF and C_p = 8 x 4 x 36 (Mpre's gate over vdd) + 4 x 30
    (Mgate_top's drain) = 1272 aF: 11432 aF. C_b must reach 0.9 / 0.1 x 4/3 = 12 times that,
    137184 aF; a 16-long capacitor has 16 x 86 + 72 = 1448 aF a unit width, so 95 wide (137560 aF;
    94 wide has 136112 aF). Its bottom plate: 95 x 16 x 8.6 + (2 x 95 + 3 x 4) x 30 = 19132 aF,
    so L_2 >= 2 x (4 x 1 / 32) x 1 pF / 19.132 fF = 13.07. One unit shorter (13) asks a 92-wide
    capacitor (12 x 11088 aF over 1448), whose 18539.2 aF bottom plate asks 13.48 units: 14 is the
    shortest. Eq. (3.70) by this count: 137560 / (137560 + 11432) = 0.9233."""
    design = _bootstrapped(32)
    assert (design.boot_w, design.cap_w, design.cap_l, design.bot_l) == (4, 95, 16, 14)
    assert _boosted_f(design) == pytest.approx(11432 * AF)
    assert _boost_f(design) == pytest.approx(137560 * AF)
    assert _bottom_f(design) == pytest.approx(19132 * AF)
    assert _bottom_length(design, LOAD_F) == pytest.approx(13.067, abs=1e-3)
    assert _boost_f(design) / (_boost_f(design) + _boosted_f(design)) == pytest.approx(0.9233, abs=1e-4)
    shorter = Params(switch_type=SwitchType.BOOTSTRAP, boot_w=4, cap_w=92, cap_l=16, bot_l=13)
    assert _bottom_length(shorter, LOAD_F) == pytest.approx(13.485, abs=1e-3) and not valid(shorter, "tsmc65")
    assert valid(design, "tsmc65") and runs.bootstrap.build() == design


def test_the_bottom_plate_switch_grows_with_the_load_it_is_sized_for() -> None:
    """L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q: twice the load asks twice the length of the
    same capacitor; the longer gate then asks a larger capacitor, whose larger bottom plate gives
    some of the length back. For 2 pF the shortest consistent pair is the first length, counting
    up, that the capacitor sized for it admits, and it is longer than 1 pF's 14 units."""
    design = _bootstrapped(32)
    assert _bottom_length(design, 2 * LOAD_F) == pytest.approx(2 * _bottom_length(design, LOAD_F))
    doubled = _bootstrapped(32, load_f=2 * LOAD_F)
    assert doubled.bot_l > design.bot_l and doubled.cap_w > design.cap_w
    assert _bottom_length(doubled, 2 * LOAD_F) <= doubled.bot_l
    assert _bottom_length(design, 2 * LOAD_F) > design.bot_l


def test_a_kit_of_other_unit_capacitances_gets_its_own_sizes() -> None:
    """A bottom plate of twice the capacitance a unit area (and no junctions) shortens the length
    the same capacitor's switch needs: C_Q = 95 x 16 x 17.2 aF = 26144 aF, L_2 >= 0.25 x 1 pF /
    26.144 fF = 9.56."""
    design = _bootstrapped(32)
    assert _bottom_length(design, LOAD_F, bottom_f=17.2 * AF, junction_f=0.0) == pytest.approx(9.562, abs=1e-3)
    assert _bootstrapped(32, bottom_f=17.2 * AF, junction_f=0.0).bot_l < design.bot_l


def test_a_switch_too_narrow_for_its_bootstrap_is_no_design() -> None:
    """The 16-unit switch (helpers 4 units, the least): the rule gives a 106-wide capacitor and a
    25-long bottom-plate switch, whose gate, 4 x (25 x 86 + 72) = 8888 aF, is 3.52 times the
    switch's own 16 x 158 = 2528 aF: past ``BOTTOM_GATE_MAX`` (2), so ``valid`` refuses it, and the
    8-unit one; the design space holds neither. A plain switch of any width is a design."""
    narrow = _bootstrapped(16)
    assert (narrow.cap_w, narrow.bot_l) == (106, 25)
    assert _gate_f(4, 25) / _gate_f(16, 1) == pytest.approx(8888 / 2528)
    assert not valid(narrow, "tsmc65") and not valid(_bootstrapped(8), "tsmc65")
    assert valid(Params(switch_type=SwitchType.NMOS, mos_w=8), "tsmc65")
    widths = sorted(
        (design.mos_w, design.mos_l)
        for design in design_space("samp", "tsmc65").values()
        if design.switch_type is SwitchType.BOOTSTRAP
    )
    assert widths == [(32, 1), (32, 2), (64, 1), (112, 1), (128, 1), (160, 1)]


def test_every_bootstrap_of_the_space_meets_the_rule() -> None:
    """Every bootstrapped design of the space: C_b / (C_b + C_G1 + C_G2 + C_p) by the count above
    0.9 ([Razavi-ADC] Eq. (3.70), p. 50) with a third of the counted load again uncounted, its
    bottom-plate switch at least the rule's length for the bench's load, and the design the
    sizing gives for its switch."""
    found = [design for design in design_space("samp", "tsmc65").values() if design.switch_type is SwitchType.BOOTSTRAP]
    assert len(found) == 6
    for design in found:
        assert valid(design, "tsmc65") and design == _bootstrapped(design.mos_w, design.mos_l)
        counted = _boosted_f(design)
        assert _boost_f(design) / (_boost_f(design) + 4 / 3 * counted) >= BOOST_MIN
        assert _bottom_length(design, LOAD_F) <= design.bot_l
