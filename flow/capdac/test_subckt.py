"""The capacitive DAC's driver bands (``subckt._driver_rows``): rows at most, balance, outline; and
the drivers' sizing against answers derived on paper: a plate's load while its stage's other plate
steps the other way (``_plate_load``), the plate of the larger drawn R C settling its own step
(``_keys``), a request drawn at most its on-resistance (``_at_most``) and its chain counted as
drawn where lowering it lengthens the chain (``_drive_r_ohm``)."""

import math
from types import SimpleNamespace

import hdl21 as h
import pytest

from . import subckt
from .params import Params
from .test_known_answers import near


def test_balanced_rows_split_the_widths_as_evenly_as_it_goes() -> None:
    widths = [9200, 7400, 4000, 3200, *[2400] * 12]
    rows = subckt._balanced(widths, 3)
    assert sorted(i for r in rows for i in r) == list(range(len(widths)))
    assert all(r == sorted(r) for r in rows)
    assert subckt._rows_width(widths, rows) <= 18000  # the lower bound is sum / 3 = 17533 nm


def test_a_band_never_takes_more_rows_than_its_cap() -> None:
    main, diff = [2400] * 16, [1000] * 16
    for stacked in (True, False):
        m, d = subckt._driver_rows(main, diff, (5000, 40000), 1800, stacked, 200)
        assert len(m) <= subckt.MAIN_ROWS and len(d) <= subckt.DIFF_ROWS
        assert sorted(i for r in m for i in r) == list(range(16)) and sorted(i for r in d for i in r) == list(range(16))


def test_the_rows_reach_past_the_capacitors_where_three_rows_do_not_fit_under_them() -> None:
    main = [2400] * 16
    m, _ = subckt._driver_rows(main, [], (5000, 40000), 1800, True)
    assert len(m) == subckt.MAIN_ROWS and subckt._rows_width(main, m) > 5000


def test_the_fewest_rows_where_more_would_not_narrow_the_outline() -> None:
    main = [1000] * 4
    m, d = subckt._driver_rows(main, [], (20000, 40000), 1800, True)
    assert len(m) == 1 and d == []


def test_a_rows_drivers_stand_over_their_stages_as_their_order_allows() -> None:
    # alone each over its target; two wanting one place share it about it; held within the extent
    assert subckt._row_places([2, 2], [3, 9], 20) == [3, 9]
    assert subckt._row_places([2, 2], [5, 5], 20) == [4, 6]
    assert subckt._row_places([2, 2], [0, 0], 20) == [1, 3]
    assert subckt._row_places([2, 2], [30, 30], 20) == [17, 19]


def test_the_routes_along_the_capacitors_end_count_where_most_pass() -> None:
    # four one-piece stages 10 wide, drivers 20 wide in one row: the row twice the stages' width,
    # its drivers reach past their stages, the middle two stages' routes and an outer one's overlap
    pieces, unit = [1, 1, 1, 1], 10
    assert subckt._crossings([20] * 4, [[0, 1, 2, 3]], pieces, unit) == 2
    # drivers as wide as their stages stand over them: no route runs along
    assert subckt._crossings([10] * 4, [[0, 1, 2, 3]], pieces, unit) == 0
    # a stage of three pieces runs along its own pieces, from its first landing to its last
    assert subckt._crossings([10, 10], [[0, 1]], [3, 1], unit) == 1


def test_a_stage_in_as_many_strips_as_pieces_is_its_pieces() -> None:
    plates = [(64.0, 0.0), (64.0, 0.0), (44.0, 20.0)]
    assert subckt._segments(plates, 3) == plates


def test_strips_keep_each_stages_plates_and_hold_no_more_than_their_length() -> None:
    plates = [[(64.0, 0.0)] * 5 + [(44.0, 20.0)], [(40.0, 24.0)], [(64.0, 0.0), (33.0, 31.0)]]
    for length in (16.0, 48.0, 64.0, 96.0, 200.0):
        for stage, strips in zip(plates, subckt._strips(plates, length), strict=True):
            assert all(m + d <= length + 1e-9 for m, d in strips)
            assert abs(sum(m for m, _ in strips) - sum(m for m, _ in stage)) < 1e-9
            assert abs(sum(d for _, d in strips) - sum(d for _, d in stage)) < 1e-9
            assert len({round(m + d, 9) for m, d in strips}) == 1  # a stage's strips one load
    # half a piece's length: each piece in two strips, each its half
    assert subckt._strips([[(44.0, 20.0)]], 32.0) == [[(22.0, 10.0), (22.0, 10.0)]]


def test_the_outline_nearest_two_to_one_within_the_area_held() -> None:
    outlines = {1.0: (100, 40), 2.0: (45, 90), 3.0: (40, 100), 4.0: (30, 160)}
    assert subckt._two_to_one(outlines, 1.0) == 3.0  # 2.0 and 3.0 in ASPECT, 3.0 the smaller; 4.0 too big
    assert subckt._two_to_one({1.0: (100, 40), 2.0: (45, 90), 0.5: (200, 20)}, 1.0) == 2.0
    # more area than GROWTH allows is never taken, however near two to one
    assert subckt._two_to_one({1.0: (100, 40), 2.0: (80, 160)}, 1.0) == 1.0
    # the plain one where another is no nearer
    assert subckt._two_to_one({1.0: (100, 40), 0.5: (100, 40)}, 1.0) == 1.0


def test_a_tie_cell_abuts_each_driver_and_both_sides_of_a_wide_one() -> None:
    """A driver's tie on its left, what stands beside it (its plate's sense inverter) between them
    and a wide driver's right tie."""
    side = h.Module(name="side")
    side.vdd, side.vss = h.Port(), h.Port()
    cell = h.ExternalModule(name="TIE", port_list=[h.Inout(name="VDD"), h.Inout(name="VSS")], paramtype=h.HasNoParams)
    inv = h.ExternalModule(name="INV", port_list=[h.Inout(name="VDD")], paramtype=h.HasNoParams)
    narrow, broad = side.add(inv()(VDD=side.vdd), name="narrow"), side.add(inv()(VDD=side.vdd), name="broad")
    sense = side.add(inv()(VDD=side.vdd), name="sense")
    entries, abut = subckt._tied_row(side, cell, [(narrow,), (broad, sense)], {"broad"}, "main0")
    names = [e.name for e in entries]
    assert names == ["Xtie_main0_0", "narrow", "Xtie_main0_1", "broad", "sense", "Xtie_main0_1r"]
    assert len(abut) == 2 and all(a.abut for a in abut)


def test_a_driver_settles_its_stage_within_its_budget_past_its_chain(monkeypatch) -> None:
    """``_drive_r_ohm``: the chain's inner inverters (each an FO4 delay), the plate's swing to
    mid-supply at the switching resistance and the rest of its k time constants at the
    on-resistance come to the budget, ``settle_ps`` over ``settle_margin``, at the kit's scale."""
    import math

    from flow.layout.devices.mosfet.table import MosfetTable

    table = MosfetTable(
        pdk="synthetic",
        vdd_v=1.0,
        switching_ohm={"NMOS/LOW": 10e3, "PMOS/LOW": 25e3},
        triode_ohm={"NMOS/LOW": 4e3, "PMOS/LOW": 10e3},
        fo4_delay_s={"LOW": 20e-12},
    )
    monkeypatch.setattr(subckt, "mosfet_table", lambda pdk: table)
    monkeypatch.setattr("flow.layout.devices.mosfet.netlist.mosfet_table", lambda pdk: table)
    monkeypatch.setattr(h.pdk, "default", lambda: None)  # no kit's row cells: each width as asked
    params, load_f, share = Params(), 100e-15, 0.375
    for scale in (1.0, 0.5):
        monkeypatch.setattr(subckt, "import_module", lambda name, scale=scale: SimpleNamespace(DRIVER_TAU_SCALE=scale))
        r_ohm = subckt._drive_r_ohm(params, share, load_f, "synthetic", False, 4.0)
        chain = len(subckt.DriverRequest(r_ohm, False, fanin=4.0).stages("synthetic"))
        k = math.log(2 ** (params.bits + 1) * share)
        settle = (chain - 1) * 20e-12 + scale * load_f * r_ohm * (k - math.log(2) + math.log(2) * 2.5)
        assert settle == pytest.approx(params.settle_ps * 1e-12 / params.settle_margin)


def test_a_plates_load_is_its_drawn_capacitances(monkeypatch) -> None:
    """``_plate_loads``: a plate's capacitance to the top plate in series with the rest of it, with
    its capacitance to the shield and the substrate, and twice its coupling to the other plate; a
    main plate's with its sense inverter's input."""
    pairs = {
        ("MAIN", "TOP"): 10e-15,
        ("DIFF", "TOP"): 1e-15,
        ("MAIN", "SHIELD"): 2e-15,
        ("DIFF", "GROUND"): 0.5e-15,
        ("DIFF", "MAIN"): 0.25e-15,
        ("SHIELD", "TOP"): 3e-15,
    }
    table = SimpleNamespace(strip=lambda layers, net_f, whole_f: (None, None), capacitances=lambda geometry: pairs)
    monkeypatch.setattr(subckt, "momcap_table", lambda pdk: table)
    route = 0.75e-15  # the kit's wiring to each plate (DRIVER_ROUTE_F), added to every plate's load
    monkeypatch.setattr(subckt, "import_module", lambda name: SimpleNamespace(DRIVER_ROUTE_F=route))
    sense = 0.4e-15  # the main plate's sense inverter's input
    monkeypatch.setattr(subckt, "least_inverter", lambda pdk: None)
    monkeypatch.setattr(subckt, "input_f", lambda pdk, request: sense)
    (main, diff), (other, _) = subckt._plate_loads("synthetic", 3, [[(1.0, 0.0)], [(1.0, 0.0)]], 1e-15, True)
    top = 2 * 14e-15
    assert main == pytest.approx(10e-15 * (top - 10e-15) / top + 2e-15 + 0.5e-15 + route + sense)
    assert diff == pytest.approx(1e-15 * (top - 1e-15) / top + 0.5e-15 + 0.5e-15 + route)
    assert other == pytest.approx(main)


def test_the_sense_inverters_row_counts_in_the_outline() -> None:
    """``_extent``: the sense inverters' row (its width) is one row more, beside the capacitors a
    row's height more; under them (stacked) none; and as wide as it is where it is the widest."""
    pair = ([[0]], [[0]])
    assert subckt._extent(pair, [1000], [800], (5000, 40000), 1800, False, 0) == (5000, 40000 + 2 * 1800)
    assert subckt._extent(pair, [1000], [800], (5000, 40000), 1800, False, 0, 6000) == (6000, 40000 + 3 * 1800)
    assert subckt._extent(pair, [1000], [800], (5000, 40000), 1800, True, 0, 3000) == (5000, 40000)


def test_a_small_stages_main_driver_settles_its_own_step_where_its_difference_driver_runs_ahead(
    monkeypatch,
) -> None:
    """``_keys``: a stage whose difference driver is drawn faster than its main driver settles (the
    least inverter on a small plate) has its main driver settle its plate's own step: a small stage
    of two plates tens of units each much stronger than its weight alone asks; a large stage, its
    main plate about its weight, about as it was."""
    from flow.layout.devices.mosfet.table import MosfetTable

    table = MosfetTable(
        pdk="synthetic",
        vdd_v=1.0,
        switching_ohm={"NMOS/LOW": 10e3, "PMOS/LOW": 25e3},
        triode_ohm={"NMOS/LOW": 4e3, "PMOS/LOW": 10e3},
        fo4_delay_s={"LOW": 20e-12},
    )
    monkeypatch.setattr(subckt, "mosfet_table", lambda pdk: table)
    monkeypatch.setattr("flow.layout.devices.mosfet.netlist.mosfet_table", lambda pdk: table)
    monkeypatch.setattr(subckt, "import_module", lambda name: SimpleNamespace(DRIVER_TAU_SCALE=1.0))
    monkeypatch.setattr(h.pdk, "default", lambda: None)  # no kit's row cells: each width as asked
    weights, loads = [1000.0, 1.0], [(60e-15, 1e-15), (5e-15, 4e-15)]
    plain = subckt._keys(Params(), "synthetic", weights, loads, True)
    own = subckt._keys(Params(), "synthetic", weights, loads, True, [(1000.5, 0.5), (32.5, 31.5)])
    assert own[1][0][0] < 0.5 * plain[1][0][0]  # the small stage's main driver: its own step
    assert own[0][0][0] == pytest.approx(plain[0][0][0], rel=0.02)  # the large one's: about its weight
    assert own[1][1] == plain[1][1]  # the difference drivers as they were


# ---- the drivers' sizing against answers derived on paper


def test_a_plate_charges_through_the_top_plate_its_stages_other_plate_moves() -> None:
    """A main plate of 64 fF and a difference plate of 16 fF to a 128 fF top plate, the main
    stepping V while the difference steps -V: the top plate moves (64 - 16) V / 128 = 0.375 V, so
    the main plate charges 64 (1 - 0.375) = 40 fF, the difference plate 16 (1 + 0.375) = 22 fF;
    with the main plate's 3 fF and the difference plate's 2 fF to the shield and 1 fF between them
    (twice: 2 fF): 45 fF and 26 fF."""
    stage = [
        {
            frozenset(("MAIN", "TOP")): 64e-15,
            frozenset(("DIFF", "TOP")): 16e-15,
            frozenset(("MAIN", "SHIELD")): 3e-15,
            frozenset(("DIFF", "SHIELD")): 2e-15,
            frozenset(("MAIN", "DIFF")): 1e-15,
        }
    ]
    assert subckt._plate_load(stage, "MAIN", "DIFF", 128e-15) == near(45e-15, rel=1e-12)
    assert subckt._plate_load(stage, "DIFF", "MAIN", 128e-15) == near(26e-15, rel=1e-12)


@pytest.fixture
def synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """A kit of triode resistances 4 and 10 kOhm a unit (N, P), switching 10 and 25 kOhm (rho 2.5),
    an FO4 of 20 ps, no time-constant scale."""
    from flow.layout.devices.mosfet.table import MosfetTable

    table = MosfetTable(
        pdk="synthetic",
        vdd_v=1.0,
        switching_ohm={"NMOS/LOW": 10e3, "PMOS/LOW": 25e3},
        triode_ohm={"NMOS/LOW": 4e3, "PMOS/LOW": 10e3},
        fo4_delay_s={"LOW": 20e-12},
    )
    monkeypatch.setattr(subckt, "mosfet_table", lambda pdk: table)
    monkeypatch.setattr("flow.layout.devices.mosfet.netlist.mosfet_table", lambda pdk: table)
    monkeypatch.setattr(subckt, "import_module", lambda name: SimpleNamespace(DRIVER_TAU_SCALE=1.0))
    monkeypatch.setattr(h.pdk, "default", lambda: None)  # no kit's row cells: each width as asked


def test_a_difference_plate_slower_than_its_main_settles_its_own_step(synthetic: None) -> None:
    """12 bits, weights 1000 and 1 (W = 1001), the small stage's plates 32.5 and 31.5 units, its
    main plate's load 1 fF and its difference plate's 8 fF. Sized for the net step, ln(2^13 / 1001)
    = 2.102 time constants, the difference driver asks 500 ps / (8 fF (2.102 + 1.5 ln 2)) = 19.9
    kOhm, drawn as one unit each (10 kOhm, the P unit's): 80 ps; the main chain (two inverters, an
    FO4 of 20 ps first) asks (500 - 20) ps / (1 fF 3.142) = 152.8 kOhm, drawn at the least (10 kOhm):
    10 ps. The difference plate settles last, so its driver settles its own 31.5 units: ln(2^13
    31.5 / 1001) = 5.552 time constants, 500 ps / (8 fF (5.552 + 1.5 ln 2)) = 9.481 kOhm (one N, two
    P units, drawn 5 kOhm: 40 ps, still the slower). The main chain keeps its net step, at the fan-in
    the larger difference driver leaves (4 less its 1.5 minimum inverters: 2.5)."""
    weights, loads = [1000.0, 1.0], [(60e-15, 1e-15), (1e-15, 8e-15)]
    keys = subckt._keys(Params(), "synthetic", weights, loads, True, [(1000.5, 0.5), (32.5, 31.5)])
    (main_r, _, main_fanin), (diff_r, _, diff_fanin) = keys[1]
    own = math.log(2**13 * 31.5 / 1001)
    assert diff_r == near(500e-12 / (8e-15 * (own + 1.5 * math.log(2))), rel=1e-9)
    assert diff_fanin == 4.0 and main_fanin == 2.5
    net = math.log(2**13 / 1001)
    assert main_r == near(480e-12 / (1e-15 * (net + 1.5 * math.log(2))), rel=1e-9)


def test_a_request_drawn_weaker_asks_for_less_until_it_is_drawn_at_most_its_resistance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where every request is drawn 1.19 times its on-resistance, a driver of at most 100 Ohm
    requests 100 / 1.19 = 84.03 Ohm (drawn at 100); one drawn below its request asks for itself."""
    monkeypatch.setattr(subckt, "drawn_ohm", lambda pdk, request: 1.19 * request.r_ohm)
    request = subckt._at_most("synthetic", 100.0, False, 4.0)
    assert request == near(100.0 / 1.19, rel=1e-9) and 1.19 * request <= 100.0 * (1 + 1e-9)
    monkeypatch.setattr(subckt, "drawn_ohm", lambda pdk, request: 0.9 * request.r_ohm)
    assert subckt._at_most("synthetic", 100.0, False, 4.0) == 100.0


def test_a_request_lowered_past_a_step_of_the_taper_counts_the_longer_chain(
    synthetic: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_drive_r_ohm``, 12 bits (a 500 ps budget), half the array's weight (k = ln(2^13 / 2) = 12
    ln 2), 100 fF of load, rho 2.5: R 100 fF (12 ln 2 - ln 2 + 2.5 ln 2) = R 100 fF 13.5 ln 2 =
    R 0.9357 ps / Ohm. Every request drawn 1.19 times its on-resistance (``_at_most`` asks for
    1 / 1.19 of R), a buffer of two inverters asked at 440 Ohm or more and of four below. No chain:
    534.3 Ohm, asked as 449.0 Ohm, two inverters, one FO4 (20 ps): 480 ps / 0.9357 = 513.0 Ohm,
    asked as 431.1 Ohm, which draws four. Counted again for four, three FO4 delays: 440 ps /
    0.9357 = 470.2 Ohm, asked as 395.1 Ohm, still four: drawn at 470.2 Ohm, 60 ps + 440 ps =
    500 ps. Where the taper's step is at 400 Ohm, 431.1 Ohm keeps two inverters: 513.0 Ohm."""
    monkeypatch.setattr(subckt, "drawn_ohm", lambda pdk, request: 1.19 * request.r_ohm)
    per_ohm = 100e-15 * 13.5 * math.log(2)
    for step_ohm, chain, expected in ((440.0, 4, 440e-12), (400.0, 2, 480e-12)):
        monkeypatch.setattr(
            subckt.DriverRequest,
            "stages",
            lambda self, pdk, step_ohm=step_ohm: [(1, 1)] * (2 if self.r_ohm >= step_ohm else 4),
        )
        r_ohm = subckt._drive_r_ohm(Params(), 0.5, 100e-15, "synthetic", False, 4.0)
        assert r_ohm == near(expected / per_ohm, rel=1e-9)
        request = subckt.DriverRequest(subckt._at_most("synthetic", r_ohm, False, 4.0), False)
        assert len(request.stages("synthetic")) == chain
        drawn = subckt.drawn_ohm("synthetic", request)
        assert drawn == near(r_ohm, rel=1e-9)
        assert (chain - 1) * 20e-12 + drawn * per_ohm == near(500e-12, rel=1e-9)
