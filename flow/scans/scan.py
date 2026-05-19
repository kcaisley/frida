"""Unified FRIDA chip scan.

CLI entry point: ``run_scan(args)``, called from ``flow/cli.py``.
Core loop: ``main_loop(chip, params)`` - backend-agnostic, operates
only through the ``Frida`` class.

Sequence values dispatched through ``chip.configure_sequencer()``:
  - "none"      → no sequencer loaded; SPI register write/readback only
  - "adc"       → full SAR conversion
  - "comp"      → continuous comp clock
  - "samp_comp" → single sample+compare
  - "calib"     → init→sample→comp→DAC→comp
  - "fastrx"    → fast_spi_rx loopback test pattern
"""

import logging
from pathlib import Path

import numpy as np

from flow.scans.chip import Frida

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]


# Backend-agnostic scan loop
def scan_loop(
    chip: Frida,
    *,
    sequence: str = "none",
    channels: list[int],
    dacmode: str = "normal",
    dacstate: list[int],
    diffcaps: bool = False,
    input_mode: str = "manual",
    vdd: float = 1.2,
    diffamp: bool = False,
    fastrx: str = "compout",
    fastrx_en_mux: str = "gpio",
    clkdiv: int = 1,
    cycles: int = 1,
    loopback: str = "none",
    fifo: str = "fastrx",
    save: bool = False,
) -> dict:
    """Run the unified scan loop across channels and input voltages.

    Steps:
      0. Release chip reset; configure loopback, fastrx source, FIFO mode
      1. Load sequencer pattern (unless ``sequence == "none"``)
      2. Build voltage table from input_mode
      3. Parse DAC state
      4. For each channel:
         a. Configure ADC, set DAC state, write ADC config, verify
         b. For each input voltage step (or once in manual mode):
            - Set vin via AWG (unless manual)
            - Trigger sequencer + capture results
      5. Optionally save NPZ to scratch/scan/

    If ``sequence == "fastrx"`` or counter-only mode, steps 1–4 are
    skipped and the FIFO is read directly (no chip config needed).

    Args:
        chip: Initialized ``Frida`` instance (any backend).
        sequence: One of ``"none"``, ``"adc"``, ``"comp"``,
            ``"samp_comp"``, ``"calib"``, ``"fastrx"``.
        channels: List of ADC channel indices [0..15].
        dacmode: ``"normal"`` (A-state only) or ``"calib"`` (A→B transition).
        dacstate: List of integer DAC state values. Length 2 for ``normal``
            (astate_p, astate_n), length 4 for ``calib`` (A_P, A_N, B_P, B_N).
        diffcaps: Whether DAC differential caps mode is enabled.
        input_mode: ``"manual"``, ``"dc"``, ``"ramp"``, ``"sine"``.
        vdd: Supply voltage in volts (used as common-mode reference).
        clkdiv: Sequencer clock divider; 1 = 200 MHz full speed.
        cycles: Number of sequence repetitions per voltage step.
            Passed directly to seq_gen REPEAT register (0 = forever).
        save: If True, also write results as NPZ to scratch/scan/.
        loopback: One of ``"none"``, ``"spi"``, ``"fastrx"``, ``"both"``.
            Enables SPI loopback, fast-RX loopback, or both.
        fifo: One of ``"fastrx"``, ``"counter"``. Selects the FASTRX FIFO
            data source: ``fastrx`` for real COMP_OUT capture, ``counter``
            for a counting-up debug sequence (FIFO/chain verification).
        fastrx: One of ``"compout"``, ``"tiehigh"``. Selects the FASTRX
            input source: ``compout`` for the external COMP_OUT pin,
            ``tiehigh`` to force fastrx_in high regardless of pin state.
        fastrx_en_mux: One of ``"gpio"`` or ``"seqout"``. Selects the
            fastrx_en source: ``"gpio"`` (default) uses gpio[6] to drive
            both the sequencer trigger and fastrx_en; ``"seqout"`` uses
            the sequencer's FASTRX_EN track for fastrx_en.

    Returns:
        Nested dict: ``{channel_index: list[np.ndarray]}`` for normal scans,
        or ``{sequence_name: list[np.ndarray]}`` for fast-RX / counter mode.
    """

    # Step 0: Reset the chip and wait
    chip.set_and_reset()

    # Step 0b: If requested, configure SPI loopback, otherwise read from sdo
    chip.set_spi_loopback(loopback == "spi" or loopback == "both")

    # Step 0c: If requested, configure fastrx input source, eiter comp_out, fastrx_test_data, or tie-high
    chip.set_fastrx_loopback(loopback == "fastrx" or loopback == "both")
    chip.set_fastrx_tiehigh(fastrx == "tiehigh")

    # Step 0c-bis: Configure fastrx_en mux source
    chip.set_fastrx_en_mux(fastrx_en_mux)

    # Step 0d: If requested, configure FIFO debug counter, otherwise just connect to fastrx output
    chip.set_fifo_debug_counter(fifo == "counter")

    # Fast RX / counter test mode. FPGA only, no Frida config or peripherals needed
    if sequence == "fastrx" or (sequence == "none" and fifo == "counter"):
        if sequence != "none":
            chip.configure_sequencer(sequence, clkdiv=clkdiv)
            chip.trigger_sequencer(repeats=cycles)
            bits = chip.read_fastrx_fifo(words=cycles)
        else:
            bits = chip.test_fastrx_fifo(words=cycles)
        return {sequence if sequence != "none" else "counter": [bits.reshape(-1, 1, 1)]}

    # Step 0e: Configure peripherals
    chip.set_diffamp(diffamp)
    chip.set_vdd(vdd)

    # Step 1: load sequencer, if requested
    if sequence != "none":
        chip.configure_sequencer(
            sequence,
            clkdiv=clkdiv,
        )

    # Step 2: Build voltage table from input_mode
    cm = vdd / 2
    if input_mode == "manual":
        voltage_entries: list[dict[str, float] | None] = [None]
    elif input_mode == "dc":
        voltage_entries = [{"diff": 0.0, "cm": cm}]
    elif input_mode == "ramp":
        voltages = np.arange(-0.005, 0.0055, 0.0005)
        voltage_entries = [{"diff": float(v), "cm": cm} for v in voltages]
    elif input_mode == "sine":
        t = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        voltage_entries = [{"diff": 0.005 * np.sin(ti), "cm": cm} for ti in t]
    else:
        raise ValueError(f"Unknown input mode {input_mode!r}")

    # Step 3: Parse DAC state
    if dacmode == "normal":
        if len(dacstate) < 2:
            raise ValueError(f"normal mode expects 2 DAC values, got {len(dacstate)}")
        astate_p, astate_n = dacstate[0], dacstate[1]
        bstate_p, bstate_n = 0x7FFF, 0x7FFF
    elif dacmode == "calib":
        if len(dacstate) < 4:
            raise ValueError(f"calib mode expects 4 DAC values, got {len(dacstate)}")
        astate_p, astate_n, bstate_p, bstate_n = dacstate[:4]
    else:
        raise ValueError(f"Unknown dacmode {dacmode!r}")

    # Step 4: Channel loop + voltage loop
    results: dict[int, list[np.ndarray]] = {ch: [] for ch in channels}

    for channel in channels:
        # Step 4a: Configure ADC, set DAC state, write SPI, read back, verify
        chip.adc_output_mux(channel)

        if sequence in ("samp_comp", "comp"):
            chip.adc_clkgate_and_mode(
                channel,
                en_init=False,
                en_samp_p=True,
                en_samp_n=True,
                en_comp=True,
                en_update=False,
                dac_mode=(dacmode == "calib"),
                dac_diffcaps=diffcaps,
            )
        else:
            chip.adc_clkgate_and_mode(
                channel,
                en_samp_p=True,
                en_samp_n=True,
                en_comp=True,
                en_update=True,
                dac_mode=(dacmode == "calib"),
                dac_diffcaps=diffcaps,
            )

        chip.adc_dac_states(
            astate_p=astate_p,
            bstate_p=bstate_p,
            astate_n=astate_n,
            bstate_n=bstate_n,
        )

        chip.write_adc_cfg()
        logger.info(
            "SPI register programmed: ch=%d, dacstate=%s, dacmode=%s, diffcaps=%s",
            channel,
            dacstate,
            dacmode,
            diffcaps,
        )

        # Step 4b: Voltage sweep
        for ventry in voltage_entries:
            # Step 4b-i: Set vin via AWG (unless manual)
            if input_mode != "manual" and ventry is not None:
                chip.set_vin(diff=ventry["diff"], cm=ventry["cm"])

            if sequence == "none" and fifo != "counter":
                continue

            # Step 4b-ii: Trigger sequencer + capture results
            chip.trigger_sequencer(repeats=cycles)
            bits = chip.read_fastrx_fifo(words=cycles)
            results[channel].append(bits)
            if input_mode == "manual":
                break

    # Step 5: Optionally save NPZ to scratch/scan/
    if save:
        outdir = REPO / "scratch" / "scan"
        outdir.mkdir(parents=True, exist_ok=True)
        np.savez(
            outdir / f"scan_{sequence}.npz",
            channels=channels,
            results={ch: [r.tolist() for r in res] for ch, res in results.items()},
            dacstate=dacstate,
            dacmode=dacmode,
            input_mode=input_mode,
            vdd=vdd,
        )
        logger.info("Results saved to %s", outdir)

    return {ch: res for ch, res in results.items()}


# CLI dispatcher — called from flow/cli.py
def run_scan(args):
    """Entry point from the CLI. ``args`` is the argparse namespace.

    Picks ``map_sim.yaml`` (SiSim over TCP to cocotb) when ``--emulate`` is
    set, otherwise ``map_fpga.yaml`` (SiTcp to real hardware).  The scan
    logic is identical in both cases.
    """
    from types import SimpleNamespace

    from basil.dut import Dut

    yaml_name = "map_sim.yaml" if args.emulate else "map_fpga.yaml"
    daq = Dut(str(REPO / "flow" / "scans" / yaml_name))
    daq.init()  # SiSim.init() blocks until the cocotb TCP server is ready

    # Instruments live in their own YAML files; load them opportunistically.
    # (Skipped in simulation — SimAWG/SimPSU are not needed for SiSim path.)
    peripherals = None
    if not args.emulate:
        peripherals_kwargs: dict = {}
        try:
            awg_dut = Dut(str(REPO / "flow" / "scans" / "map_awg.yaml"))
            awg_dut.init()
            peripherals_kwargs["awg"] = awg_dut["awg"]
        except Exception as exc:
            logger.warning("AWG not available: %s", exc)
        peripherals = SimpleNamespace(**peripherals_kwargs) if peripherals_kwargs else None

    chip = Frida(daq, peripherals)

    return scan_loop(
        chip,
        sequence=args.sequence,
        channels=args.channel,
        dacmode=args.dacmode,
        dacstate=args.dacstate,
        diffcaps=args.diffcaps,
        input_mode=args.input_mode,
        vdd=args.vdd or 1.2,
        diffamp=args.diffamp or False,
        fastrx=args.fastrx or "compout",
        fastrx_en_mux=args.fastrx_en_mux,
        clkdiv=args.clkdiv,
        cycles=args.cycles,
        loopback=args.loopback,
        fifo=args.fifo,
        save=args.save,
    )
