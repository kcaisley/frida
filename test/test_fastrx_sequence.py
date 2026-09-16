"""Exercise the production Basil sequencer and FastRX RTL together."""

from pathlib import Path

from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]


def test_fastrx_sequence(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(ROOT / "test/cocotb")
    monkeypatch.syspath_prepend(ROOT)
    rtl = ROOT / "libs/basil/basil/firmware/modules"
    runner = get_runner("icarus")
    runner.build(
        sources=[
            rtl / "seq_gen/seq_gen_core.v",
            rtl / "fast_spi_rx/fast_spi_rx_core.v",
            ROOT / "test/rtl/fastrx_sequence_tb.v",
        ],
        includes=[rtl],
        hdl_toplevel="fastrx_sequence_tb",
        build_dir=tmp_path,
        build_args=["-g2005"],
        always=True,
    )
    runner.test(
        test_module="fastrx_sequence_cocotb", hdl_toplevel="fastrx_sequence_tb", build_dir=tmp_path, test_dir=tmp_path
    )
