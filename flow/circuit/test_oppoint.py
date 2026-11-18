"""The operating-point checks of a bench's transistors (``flow.circuit.oppoint``): saturation
margins, junction bias and terminal voltages, on synthetic operating points of known answers; the
Spectre diagnostic is ``test_spectre``'s."""

from datetime import UTC, datetime

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest
from hdl21.primitives import MosType

from flow.circuit import oppoint, spectre
from flow.circuit.oppoint import Junction, Region, Terminals
from flow.pipeline import Meas, MeasInfo, Sweep, SweepKind


def _signals(values: dict[str, list[float]]) -> dict[str, np.ndarray]:
    """``<device>_<value>`` keywords as signals (``Msat:vds``), each device's threshold as BSIM
    writes it where not given (0.4 V; -0.4 V for a PMOS, a device named ``Mp...``)."""
    v = {name.replace("_", ":", 1): np.asarray(value, dtype=float) for name, value in values.items()}
    count = len(next(iter(v.values())))
    for device in {name.split(":")[0] for name in v}:
        v.setdefault(f"{device}:vth", np.full(count, -0.4 if device.startswith("Mp") else 0.4))
    return v


def _op(**values: float) -> Sweep:
    """An operating point of ``<device>_<value>=number`` keywords (``Msat_vds=0.8``): ``_signals``."""
    return Sweep(kind=SweepKind.OP, x=np.zeros(0), v=_signals({name: [value] for name, value in values.items()}))


def test_a_margin_is_v_ds_over_v_d_sat_positive_when_saturated_for_either_type() -> None:
    """An NMOS's margin is V_DS - V_D,sat, a PMOS's -V_DS - |V_D,sat| (Spectre writes both of a
    PMOS's negative; a model that writes its V_D,sat positive reads the same); the triode devices
    are the unsaturated ones, with their margins."""
    op = _op(
        Mn_vds=0.8,
        Mn_vdsat=0.2,
        Mntri_vds=0.05,
        Mntri_vdsat=0.2,
        Mp_vds=-0.8,
        Mp_vdsat=-0.21,
        Mpother_vds=-0.8,
        Mpother_vdsat=0.21,
        Mptri_vds=-0.05,
        Mptri_vdsat=-0.21,
    )
    nmos, pmos = MosType.NMOS, MosType.PMOS
    devices = {"Mn": nmos, "Mntri": nmos, "Mp": pmos, "Mpother": pmos, "Mptri": pmos}
    found = oppoint.saturation(op, devices)
    expected = {"Mn": 0.6, "Mntri": -0.15, "Mp": 0.59, "Mpother": 0.59, "Mptri": -0.16}
    assert found.least_v == pytest.approx(expected, abs=1e-12)
    assert found.unsaturated == pytest.approx({"Mntri": -0.15, "Mptri": -0.16}, abs=1e-12)
    assert found.region == {}


def test_a_device_whose_drain_is_on_the_wrong_side_is_out_of_saturation() -> None:
    """An NMOS with its drain below its source (V_DS < 0), or a PMOS with its drain above (V_DS >
    0), conducts the other way: no current source, whatever its V_D,sat."""
    op = _op(Mn_vds=-0.3, Mn_vdsat=0.1, Mp_vds=0.3, Mp_vdsat=-0.1)
    found = oppoint.saturation(op, {"Mn": MosType.NMOS, "Mp": MosType.PMOS})
    assert found.unsaturated == pytest.approx({"Mn": -0.4, "Mp": -0.4}, abs=1e-12)


def test_margins_run_over_the_points_of_every_sweep_in_order() -> None:
    """A DC sweep's points, and the operating points of several runs (a supply's corners), one
    margin each in their order: a device saturated at two points and in triode at the third is
    unsaturated, with its least margin."""
    dc = Sweep(
        kind=SweepKind.DC,
        x=np.array([0.9, 1.0]),
        v=_signals({"Mtail_vds": [0.15, 0.3], "Mtail_vdsat": [0.18, 0.18]}),
    )
    corner = _op(Mtail_vds=0.25, Mtail_vdsat=0.18)
    found = oppoint.saturation([dc, corner], {"Mtail": MosType.NMOS})
    np.testing.assert_allclose(found.margin_v["Mtail"], [-0.03, 0.12, 0.07], atol=1e-12)
    assert found.unsaturated == pytest.approx({"Mtail": -0.03}, abs=1e-12)


def test_spectres_region_flags_off_triode_and_breakdown_but_not_subthreshold() -> None:
    """Spectre's region, where the run saved it (its numbers 0 to 4: off, triode, saturation,
    subthreshold, breakdown): a device it calls triode, off or in breakdown is flagged even with a
    margin above zero; one below threshold whose V_DS clears its V_D,sat is a current source."""
    numbers = {"Moff": 0, "Mtri": 1, "Msat": 2, "Msub": 3, "Mbreak": 4}
    values = {}
    for device, number in numbers.items():
        values |= {f"{device}_vds": 0.3, f"{device}_vdsat": 0.1, f"{device}_region": float(number)}
    found = oppoint.saturation(_op(**values), dict.fromkeys(numbers, MosType.NMOS))
    assert found.region == {
        "Moff": (Region.OFF,),
        "Mtri": (Region.TRIODE,),
        "Msat": (Region.SATURATION,),
        "Msub": (Region.SUBTHRESHOLD,),
        "Mbreak": (Region.BREAKDOWN,),
    }
    assert set(found.unsaturated) == {"Moff", "Mtri", "Mbreak"}


def test_missing_values_and_other_analyses_are_refused() -> None:
    """A device the run did not save is named with the remedy; an AC sweep is no operating point."""
    remedy = r"lack Mb:vds, Mb:vth, Mb:vdsat or vdss: the run saves them with flow.circuit.oppoint.saves"
    with pytest.raises(ValueError, match=remedy):
        oppoint.saturation(_op(Ma_vds=0.3, Ma_vdsat=0.1), {"Ma": MosType.NMOS, "Mb": MosType.NMOS})
    ac = Sweep(kind=SweepKind.AC, x=np.array([1.0]), v={"Ma:vds": np.array([1.0 + 0j])})
    with pytest.raises(ValueError, match="come from OP or DC, not AC"):
        oppoint.saturation(ac, {"Ma": MosType.NMOS})
    with pytest.raises(ValueError, match="at least one"):
        oppoint.saturation([], {"Ma": MosType.NMOS})


def test_a_bench_saves_each_devices_values_where_spectre_has_them_and_the_run_takes_psf_ascii(tmp_path) -> None:
    """``mos_devices`` finds every transistor of a module by its path, inside its instances too;
    ``saves`` names each one's ``VALUES`` below the DUT, after the bench's compile: the device itself
    where the kit names its model directly, the one instance inside where the run's device file
    wraps it in a subckt (a kit's own subckt around one transistor; an inline subckt, or a SPICE one that
    names no device of the bench, leaves it as it is); a bench not yet compiled is refused. A run
    that saves them writes PSF ASCII, which holds an operating point alone and a region."""
    inner = h.Module(name="SatInner")
    inner.d, inner.g, inner.s = h.Signal(), h.Signal(), h.Signal()
    inner.Mn = h.Nmos()(d=inner.d, g=inner.g, s=inner.s, b=inner.s)
    outer = h.Module(name="SatOuter")
    outer.a, outer.b, outer.c = h.Signal(), h.Signal(), h.Signal()
    outer.Mp = h.Pmos()(d=outer.a, g=outer.b, s=outer.c, b=outer.c)
    outer.xlatch = inner(d=outer.a, g=outer.b, s=outer.c)
    outer.cload = h.primitives.C(c=1e-15)(p=outer.a, n=outer.c)
    bench = h.Module(name="SatBench")
    bench.a, bench.b, bench.c = h.Signal(), h.Signal(), h.Signal()
    bench.dut = outer()
    devices = oppoint.mos_devices(outer)
    assert devices == {"Mp": MosType.PMOS, "xlatch.Mn": MosType.NMOS}
    with pytest.raises(ValueError, match=r"Mp is no kit device yet: compile the bench \(h.pdk.compile\)"):
        oppoint.saves(devices, bench, [])

    # the bench as a kit compiles it: each transistor a kit's device, by its name
    def device(name: str) -> h.ExternalModuleCall:
        ports = [h.Port(name=port) for port in "dgsb"]
        return h.ExternalModule(name=name, port_list=ports)(h.NoParams)

    outer.Mp.of, inner.Mn.of = device("pch"), device("nmos_hs")
    files = tmp_path / "devices.scs"
    files.write_text(
        "simulator lang=spectre\n"
        "subckt pch (d g s b)\nparameters w=40n l=30n nf=1\n    M0 (d g s b) pch_mac w=w l=l nf=nf\nends pch\n"
        "inline subckt nch (d g s b)\n    nch (d g s b) nch_mac\nends nch\n"
        "simulator lang=spice\n.subckt NMOS_HS_4 d g s b w=1u l=150n\nm0 d g s b nmos_hs w=w l=l\n.ends NMOS_HS_4\n"
        "simulator lang=spectre\n"
    )
    includes = [hs.Lib(path=tmp_path / "models.scs", section="tt"), hs.Include(path=files)]
    assert oppoint.wrappers(includes) == {"pch": "M0", "nmos_hs_4": "m0"}
    found = oppoint.saves(devices, bench, includes)
    assert found[: len(oppoint.VALUES)] == [f"xtop.dut.Mp.M0:{value}" for value in oppoint.VALUES]
    assert found[len(oppoint.VALUES) :] == [f"xtop.dut.xlatch.Mn:{value}" for value in oppoint.VALUES]
    assert oppoint.saves(["dut.Mp"], bench, includes, prefix="xtop.")[0] == "xtop.dut.Mp.M0:vgs"
    with pytest.raises(ValueError, match="dut.Mq is no instance of SatBench"):
        oppoint.saves(["Mq"], bench, includes)
    op = hs.Op(name="op")
    assert spectre.raw_format([op, hs.Save(["xtop.out", "xtop.vdd:p"])]) == "nutbin"
    assert spectre.raw_format([op, hs.Save(found)]) == "psfascii"


def test_a_kits_wrapper_and_a_pmos_written_as_an_nmos_read_as_their_own() -> None:
    """A device's values Spectre has inside the kit's wrapper (``Mn.M0:vds``) are the device's; a
    PMOS whose model writes its voltages as an NMOS's (IHP's PSP 103: V_TH, V_GS and V_DS positive
    for a PMOS that is on) reads as one that writes them as they are: the same margin, junctions
    and terminals. A PSP 102 device's V_D,sat is its ``vdss``."""
    natural = _op(
        Mn_vgs=0.7, Mn_vds=0.8, Mn_vbs=0.0, Mn_vdsat=0.2,
        Mp_vgs=-0.7, Mp_vds=-0.8, Mp_vbs=-0.4, Mp_vdsat=-0.25, Mp_vth=-0.39,
    )  # fmt: skip
    written = _op(
        **{"Mn.M0_vgs": 0.7, "Mn.M0_vds": 0.8, "Mn.M0_vbs": 0.0, "Mn.M0_vdss": 0.2},
        Mp_vgs=0.7, Mp_vds=0.8, Mp_vbs=0.4, Mp_vdsat=0.25, Mp_vth=0.39,
    )  # fmt: skip
    devices = {"Mn": MosType.NMOS, "Mp": MosType.PMOS}
    for op in (natural, written):
        assert oppoint.saturation(op, devices).least_v == pytest.approx({"Mn": 0.6, "Mp": 0.55})
        found = oppoint.stress(op, devices, nominal_v=1.2)
        assert found.forward == {"Mp": (Junction.SOURCE, pytest.approx(0.4))}
        assert {pair: float(value[0]) for pair, value in found.terminal_v["Mp"].items()} == pytest.approx(
            {Terminals.GS: 0.7, Terminals.GD: 0.1, Terminals.DS: 0.8, Terminals.GB: 0.3}
        )


def test_a_region_number_spectre_has_no_region_for_is_refused_naming_the_device() -> None:
    """A region past 4, a fraction or NaN is no region of Spectre's: the error names the device."""
    for number in (5.0, 1.5, float("nan")):
        with pytest.raises(ValueError, match=f"Mtail's region is {number}, none of Spectre's 0 to 4"):
            oppoint.spectre_region(number, "Mtail")


def _tran(**values: list[float]) -> Meas:
    """A measurement whose transient holds ``<device>_<value>=[...]`` keywords, one value a time point."""
    count = len(next(iter(values.values())))
    return Meas(
        group=None,
        index=None,
        dut=None,
        info=MeasInfo(backend="spice", timestamp_utc=datetime.now(UTC)),
        param=None,
        time_s=np.arange(count) * 1e-9,
        v=_signals(values),
    )


def test_a_junction_forward_biased_past_0p3_v_is_flagged_with_the_sign_of_its_type() -> None:
    """An NMOS's source junction forward-biased by V_BS, its drain's by V_BD = V_BS - V_DS; a
    PMOS's by -V_BS and -V_BD (its n-well below its source or drain). Reverse bias and 0.3 V or
    less of forward bias pass; past it, the device is named with the junction and its bias."""
    op = _op(
        # NMOS: bulk at its source (0), a drain 0.4 V below the bulk (V_DS -0.4: V_BD 0.4), a source
        # junction 0.35 V forward, a source junction just at the limit
        Mok_vgs=0.6, Mok_vds=0.5, Mok_vbs=0.0,
        Mdrain_vgs=0.6, Mdrain_vds=-0.4, Mdrain_vbs=0.0,
        Msource_vgs=0.6, Msource_vds=0.5, Msource_vbs=0.35,
        Medge_vgs=0.6, Medge_vds=0.5, Medge_vbs=0.3,
        # PMOS: its well at its source, its well 0.5 V below its source, its drain 0.32 V above its well
        Mpok_vgs=-0.6, Mpok_vds=-0.5, Mpok_vbs=0.0,
        Mpsource_vgs=-0.6, Mpsource_vds=-0.5, Mpsource_vbs=-0.5,
        Mpdrain_vgs=-0.6, Mpdrain_vds=0.32, Mpdrain_vbs=0.0,
        # a PMOS whose V_BS is positive (its well above its source) is reverse-biased
        Mpreverse_vgs=-0.6, Mpreverse_vds=-0.5, Mpreverse_vbs=0.4,
    )  # fmt: skip
    nmos, pmos = MosType.NMOS, MosType.PMOS
    devices = dict.fromkeys(("Mok", "Mdrain", "Msource", "Medge"), nmos) | dict.fromkeys(
        ("Mpok", "Mpsource", "Mpdrain", "Mpreverse"), pmos
    )
    found = oppoint.stress(op, devices, nominal_v=1.2)
    assert found.forward_limit_v == oppoint.FORWARD_BIAS_V == 0.3
    assert found.forward == {
        "Mdrain": (Junction.DRAIN, pytest.approx(0.4)),
        "Msource": (Junction.SOURCE, pytest.approx(0.35)),
        "Mpsource": (Junction.SOURCE, pytest.approx(0.5)),
        "Mpdrain": (Junction.DRAIN, pytest.approx(0.32)),
    }
    np.testing.assert_allclose(found.junction_v["Mpreverse"][Junction.SOURCE], [-0.4])
    np.testing.assert_allclose(found.junction_v["Mpreverse"][Junction.DRAIN], [-0.9])
    assert found.overstressed == {}


def test_a_terminal_pair_past_the_runs_largest_supply_is_flagged() -> None:
    """|V_GS|, |V_GD| = |V_GS - V_DS|, |V_DS| and |V_GB| = |V_GS - V_BS| bounded by the nominal
    supply times 1.1 (1.32 V at 1.2 V): a gate at the supply over a drain pulled below ground (V_GD
    1.4 V), a PMOS whose V_DS is -1.35 V, a gate 1.25 V below a bulk 0.2 V above its source (V_GB
    -1.45 V); 1.3 V on every pair passes."""
    op = _op(
        Mok_vgs=1.3, Mok_vds=0.0, Mok_vbs=0.0,
        Mgd_vgs=1.2, Mgd_vds=-0.2, Mgd_vbs=-0.2,
        Mpds_vgs=-1.0, Mpds_vds=-1.35, Mpds_vbs=0.0,
        Mpgb_vgs=-1.25, Mpgb_vds=-0.1, Mpgb_vbs=0.2,
    )  # fmt: skip
    nmos, pmos = MosType.NMOS, MosType.PMOS
    found = oppoint.stress(op, {"Mok": nmos, "Mgd": nmos, "Mpds": pmos, "Mpgb": pmos}, nominal_v=1.2)
    assert found.terminal_limit_v == pytest.approx(1.2 * oppoint.SUPPLY_CORNER_MAX) == pytest.approx(1.32)
    assert found.overstressed == {
        "Mgd": (Terminals.GD, pytest.approx(1.4)),
        "Mpds": (Terminals.DS, pytest.approx(1.35)),
        "Mpgb": (Terminals.GB, pytest.approx(1.45)),
    }
    np.testing.assert_allclose(
        [found.terminal_v["Mok"][pair][0] for pair in Terminals], [1.3, 1.3, 0.0, 1.3], atol=1e-12
    )
    # the same voltages within a 1.8 V run's limit
    assert oppoint.stress(op, {"Mgd": nmos, "Mpds": pmos, "Mpgb": pmos}, nominal_v=1.8).overstressed == {}


def test_junctions_and_terminals_run_over_a_transients_every_point_and_the_operating_points() -> None:
    """A transient's every time point (a measurement's own signals) and the operating points, in
    order: a drain that swings 0.45 V below ground for one point forward-biases its junction there
    (an NMOS's V_BD), and a gate that kicks past the limit for one point overstresses it; the
    largest over the points is reported."""
    tran = _tran(Msw_vgs=[0.0, 1.2, 0.0, 0.0], Msw_vds=[1.2, 0.0, -0.45, 1.2], Msw_vbs=[0.0, 0.0, 0.0, 0.0])
    op = _op(Msw_vgs=1.4, Msw_vds=0.0, Msw_vbs=0.0)
    found = oppoint.stress([tran, op], {"Msw": MosType.NMOS}, nominal_v=1.2)
    np.testing.assert_allclose(found.junction_v["Msw"][Junction.DRAIN], [-1.2, 0.0, 0.45, -1.2, 0.0])
    assert found.forward == {"Msw": (Junction.DRAIN, pytest.approx(0.45))}
    assert found.overstressed == {"Msw": (Terminals.GS, pytest.approx(1.4))}
    with pytest.raises(ValueError, match=r"lack Mx:vgs, Mx:vds, Mx:vbs, Mx:vth: the run saves"):
        oppoint.stress(tran, {"Mx": MosType.NMOS}, nominal_v=1.2)
    with pytest.raises(ValueError, match="come from OP or DC or a measurement's transient, not AC"):
        oppoint.stress(Sweep(kind=SweepKind.AC, x=np.array([1.0])), {"Msw": MosType.NMOS}, nominal_v=1.2)
    # a transient is no operating point for a saturation margin
    with pytest.raises(ValueError, match="saturation margins come from OP or DC, not Meas"):
        oppoint.saturation([tran], {"Msw": MosType.NMOS})  # type: ignore[list-item]
