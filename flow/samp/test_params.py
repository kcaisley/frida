"""The sizing of a bootstrapped switch (``params._bootstrapped``) and the designs ``params.valid``
admits: each expected value worked by hand from the unit capacitances (``GATE_F`` 93 aF a unit area,
a channel ``GATE_SHORT`` 0.28 of a unit short of its gate, ``OVERLAP_F`` 36 aF and ``JUNCTION_F``
30 aF a unit width, ``BOTTOM_F`` 8.6 aF a unit area), ``BOTTOM_LIFT`` 3 and [Razavi-ADC] Eq. (3.69),
p. 49 and Eq. (3.70), p. 50. Capacitances are compared in attofarads: pytest.approx's default
absolute tolerance, 1e-12, is above any value in farads here."""

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
    _fixed_f,
    _gate_f,
    valid,
)

AF = 1e-18


def test_a_gate_is_its_area_and_its_two_overlaps() -> None:
    """[Razavi-ADC] Eq. (3.69), p. 49: C_G = (W L) C_ox + 2 W C_ov, L the channel's length, 0.28
    of a unit short of the drawn one ([Razavi-Analog] Sec. 2.1.2, p. 8). 32 by 1 units:
    32 x (0.72 x 93 + 2 x 36) = 32 x 138.96 = 4446.72 aF; 4 by 13: 4 x (12.72 x 93 + 72) =
    4 x 1254.96 = 5019.84 aF; with no side diffusion and no overlap, 32 x 100 = 3200 aF."""
    assert _gate_f(32, 1) / AF == pytest.approx(4446.72)
    assert _gate_f(4, 13) / AF == pytest.approx(5019.84)
    assert _gate_f(32, 1, gate_f=100 * AF, short=0.0, overlap_f=0.0) / AF == pytest.approx(3200)


def test_the_boosted_nodes_load_counts_every_device_on_them() -> None:
    """The 32-unit switch's helpers are 4 units wide. C_p to nodes that stay put (``_fixed_f``):
    Mpre, 8 helpers wide, its gate over vdd and its drain's junction, 32 x (36 + 30) = 2112 aF;
    Mgate_top's drain and the pull-down stack's ten junctions, 4 x 11 x 30 = 1320 aF; the five
    overlaps of the stack's gates that stay put, 4 x 5 x 36 = 720 aF; Mgate_off_dummy's gate,
    4 x 138.96 = 555.84 aF: 4707.84 aF. With MN's gate (4446.72 aF), Mbot_in's 13 long
    (5019.84 aF) and Mgate's (555.84 aF) the boost capacitor shares its charge with 14730.24 aF
    ([Razavi-ADC] Eq. (3.69), (3.70), p. 49-50, C_GS3 + C_GD3 in C_p)."""
    design = Params(switch_type=SwitchType.BOOTSTRAP, boot_w=4, cap_w=116, cap_l=16, bot_l=13)
    assert _fixed_f(design) / AF == pytest.approx(4707.84)
    assert _boosted_f(design) / AF == pytest.approx(14730.24)
    assert (_boosted_f(design) - _fixed_f(design)) / AF == pytest.approx(4446.72 + 5019.84 + 555.84)


def test_the_32_unit_bootstrap_by_hand() -> None:
    """The 32 by 1 switch, helpers 4 units, into 1 pF. With Mbot_in 13 long the boosted nodes
    carry 14730.24 aF (the test above). C_b must reach 0.9 / 0.1 x 4/3 = 12 times that,
    176762.88 aF; a 16-long capacitor has 15.72 x 93 + 72 = 1533.96 aF a unit width, so 116 wide
    (177939.36 aF; 115 wide has 176405.4 aF). Its bottom plate: to the substrate 116 x 16 x 8.6 +
    (2 x 116 + 3 x 4) x 30 = 23281.6 aF; the control node 4 x (3 x 30 + 4 x 36) + 555.84 / 2 =
    1213.92 aF; through C_b the 4707.84 aF that stay put and MN's and Mbot_in's overlaps of vin,
    36 x 36 = 1296 aF: 177939.36 x 6003.84 / 183943.2 = 5807.88 aF. C_Q = 30303.40 aF, so
    L_2 >= 3 x (4 x 1 / 32) x 1 pF / 30.3034 fF = 12.375. One unit shorter (12) asks a 113-wide
    capacitor (12 x 14358.24 aF over 1533.96), whose 29705.57 aF asks 12.624 units: 13 is the
    shortest. Eq. (3.70) by this count: 177939.36 / (177939.36 + 14730.24) = 0.9235."""
    design = _bootstrapped(32)
    assert (design.boot_w, design.cap_w, design.cap_l, design.bot_l) == (4, 116, 16, 13)
    assert _boost_f(design) / AF == pytest.approx(177939.36)
    assert _bottom_f(design) / AF == pytest.approx(30303.40, rel=1e-6)
    assert _bottom_length(design, LOAD_F) == pytest.approx(12.375, abs=1e-3)
    assert _boost_f(design) / (_boost_f(design) + _boosted_f(design)) == pytest.approx(0.9235, abs=1e-4)
    shorter = Params(switch_type=SwitchType.BOOTSTRAP, boot_w=4, cap_w=113, cap_l=16, bot_l=12)
    assert _bottom_length(shorter, LOAD_F) == pytest.approx(12.624, abs=1e-3) and not valid(shorter, "tsmc65")
    assert valid(design, "tsmc65") and runs.bootstrap.build() == design


def test_the_bottom_plate_switch_grows_with_the_load_it_is_sized_for() -> None:
    """L_2 >= BOTTOM_LIFT (W_2 L_1 / W_1) C_L / C_Q: twice the load asks twice the length of the
    same capacitor; the longer gate then asks a larger capacitor, whose larger bottom plate gives
    some of the length back. For 2 pF the shortest consistent pair is the first length, counting
    up, that the capacitor sized for it admits, and it is longer than 1 pF's 13 units. A design
    holds for its load or a smaller one: at half the load the same switch asks half the length."""
    design = _bootstrapped(32)
    assert _bottom_length(design, 2 * LOAD_F) == pytest.approx(2 * _bottom_length(design, LOAD_F))
    doubled = _bootstrapped(32, load_f=2 * LOAD_F)
    assert doubled.bot_l > design.bot_l and doubled.cap_w > design.cap_w
    assert _bottom_length(doubled, 2 * LOAD_F) <= doubled.bot_l
    assert _bottom_length(design, 2 * LOAD_F) > design.bot_l
    assert _bottom_length(design, LOAD_F / 2) == pytest.approx(_bottom_length(design, LOAD_F) / 2)
    assert _bottom_length(design, LOAD_F / 2) <= design.bot_l


def test_a_kit_of_other_unit_capacitances_gets_its_own_sizes() -> None:
    """A bottom plate of twice the capacitance a unit area and no junctions shortens the length the
    same capacitor's switch needs: to the substrate 116 x 16 x 17.2 = 31923.2 aF; the control
    node 4 x 4 x 36 + 277.92 = 853.92 aF; through C_b what stays put, 32 x 36 + 4 x 5 x 36 +
    555.84 + 36 x 36 = 3723.84 aF, 177939.36 x 3723.84 / 181663.2 = 3647.51 aF: C_Q = 36424.63 aF,
    L_2 >= 0.375 x 1 pF / 36.4246 fF = 10.295. Sized with those units, the boosted nodes carry
    no junctions (12450.24 aF with Mbot_in 13 long: a capacitor 12 x 12450.24 / 1533.96 = 97.4, so
    98 wide); 12 long would ask a 95-wide capacitor whose 30628.97 aF asks 12.24 units, so the
    length stays 13. A current ratio of 2 in place of 3 asks two thirds of the length."""
    design = _bootstrapped(32)
    assert _bottom_length(design, LOAD_F, bottom_f=17.2 * AF, junction_f=0.0) == pytest.approx(10.295, abs=1e-3)
    other = _bootstrapped(32, bottom_f=17.2 * AF, junction_f=0.0)
    assert (other.cap_w, other.bot_l) == (98, 13)
    assert _bottom_length(design, LOAD_F, lift=2.0) == pytest.approx(2 / 3 * _bottom_length(design, LOAD_F))
    assert _bootstrapped(32, lift=2.0).bot_l < design.bot_l


def test_a_switch_too_narrow_for_its_bootstrap_is_no_design() -> None:
    """The 16-unit switch (helpers 4 units, the least): the rule gives a 130-wide capacitor and a
    24-long bottom-plate switch, whose gate, 4 x (23.72 x 93 + 72) = 9111.84 aF, is 4.10 times the
    switch's own 16 x 138.96 = 2223.36 aF: past ``BOTTOM_GATE_MAX`` (2), so ``valid`` refuses it, and the
    8-unit one; the design space holds neither. A plain switch of any width is a design."""
    narrow = _bootstrapped(16)
    assert (narrow.cap_w, narrow.bot_l) == (130, 24)
    assert _gate_f(4, 24) / _gate_f(16, 1) == pytest.approx(9111.84 / 2223.36)
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
