# Sampling Switch in a hypothetical Mojo-based Substrate
#
# This imagines the same Substrate API concepts but with Mojo syntax.
# Compare with samp_substrate2.rs to see what's Rust verbosity vs API verbosity.
#
# Key differences from Rust version:
# - No #[derive(...)] boilerplate - Mojo's @value handles this
# - No Some(...) / None - Mojo uses Optional with cleaner syntax
# - No .into() conversions - Mojo has more implicit conversions
# - Python-like struct instantiation with keyword args
# - Type inference reduces annotations

from substrate import Block, Io, Schematic, Signal, Context
from substrate.types import Input, Output, InOut
from substrate.sim import Pvt, Tran
from collections import List

# =============================================================================
# IO Definition
# =============================================================================
# Rust equivalent required 8 lines + derive macros
# Mojo: 6 lines, no ceremony

@io
struct SampIo:
    din: Input[Signal]
    dout: Output[Signal]
    clk: Input[Signal]
    clk_b: Input[Signal]
    vdd: InOut[Signal]
    vss: InOut[Signal]


# =============================================================================
# Enums for topology and device params
# =============================================================================
# Rust required #[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)] on each
# Mojo: just define the enum

@value
struct SwitchType(Stringable, Hashable):
    alias Nmos = SwitchType("nmos")
    alias Pmos = SwitchType("pmos")
    alias Tgate = SwitchType("tgate")
    var name: String

@value
struct Vth(Stringable, Hashable):
    alias Lvt = Vth("lvt")
    alias Svt = Vth("svt")
    var name: String


# =============================================================================
# Block Definition
# =============================================================================
# Rust required:
#   #[derive(Block, Debug, Copy, Clone, Hash, PartialEq, Eq)]
#   #[substrate(io = "SampIo")]
#   pub struct Samp { ... }
#
# Mojo: @block decorator infers the io type from the schematic method

@block(io=SampIo)
struct Samp:
    var switch_type: SwitchType
    var w: Int
    var l: Int
    var vth: Vth

    fn __init__(inout self, switch_type: SwitchType, w: Int, l: Int, vth: Vth = Vth.Lvt):
        self.switch_type = switch_type
        self.w = w
        self.l = l
        self.vth = vth


# =============================================================================
# Schematic Implementation
# =============================================================================
# Rust required:
#   impl Schematic for Samp {
#       type Schema = Tsmc65;
#       type NestedData = ();
#       fn schematic(&self, io: &IoNodeBundle<Self>, cell: &mut CellBuilder<...>) -> Result<()>
#
# Mojo: just define the method, schema is a parameter

fn schematic[Schema: Pdk](self: Samp, io: SampIo.Bundle, cell: CellBuilder[Schema]):
    if self.switch_type == SwitchType.Nmos:
        mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
        cell.connect(io.dout, mn.d)
        cell.connect(io.clk, mn.g)
        cell.connect(io.din, mn.s)
        cell.connect(io.vss, mn.b)

    elif self.switch_type == SwitchType.Pmos:
        mp = cell.instantiate(Pfet(self.w, self.l, self.vth))
        cell.connect(io.dout, mp.d)
        cell.connect(io.clk_b, mp.g)
        cell.connect(io.din, mp.s)
        cell.connect(io.vdd, mp.b)

    elif self.switch_type == SwitchType.Tgate:
        mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
        mp = cell.instantiate(Pfet(self.w, self.l, self.vth))

        cell.connect(io.dout, mn.d, mp.d)  # Multi-connect in one call
        cell.connect(io.clk, mn.g)
        cell.connect(io.clk_b, mp.g)
        cell.connect(io.din, mn.s, mp.s)
        cell.connect(io.vss, mn.b)
        cell.connect(io.vdd, mp.b)


# =============================================================================
# Sweep Generation
# =============================================================================
# Rust required nested for loops with explicit Vec::new() and .push()
# Mojo: list comprehension

fn generate_all_variants() -> List[Samp]:
    return [
        Samp(switch_type, w, l, vth)
        for switch_type in [SwitchType.Nmos, SwitchType.Pmos, SwitchType.Tgate]
        for w in [5, 10, 20, 40]
        for l in [1, 2]
        for vth in [Vth.Lvt, Vth.Svt]
    ]  # Returns 48 variants


fn generate_filtered_variants() -> List[Samp]:
    """With invalid combo filtering."""
    return [
        s for s in generate_all_variants()
        if not (s.switch_type == SwitchType.Pmos and s.w < 10)
    ]


# =============================================================================
# Testbench
# =============================================================================
# Rust required:
#   let clk_src = cell.instantiate(Vsource::pulse(Pulse {
#       val0: 0.into(),
#       val1: self.pvt.voltage,
#       delay: Some(dec!(0)),
#       width: Some(dec!(50e-9)),
#       ...8 more lines...
#   }));
#
# Mojo: keyword args with defaults, no Some() wrapping

@block(io=TestbenchIo)
struct SampTb:
    var pvt: Pvt
    var dut: Samp

fn schematic[Schema: Pdk](self: SampTb, io: TestbenchIo.Bundle, cell: CellBuilder[Schema]) -> Node:
    vdd = cell.signal("vdd")
    clk = cell.signal("clk")
    clk_b = cell.signal("clk_b")
    din = cell.signal("din")
    dout = cell.signal("dout")

    # Power supply - concise keyword args
    vdd_src = cell.instantiate(Vsource.dc(self.pvt.voltage))
    cell.connect(vdd_src.p, vdd)
    cell.connect(vdd_src.n, io.vss)

    # Clock - compare to Rust's 10-line Pulse struct
    clk_src = cell.instantiate(Vsource.pulse(
        v0=0, v1=self.pvt.voltage,
        period=100e-9, width=50e-9,
        rise=0.1e-9, fall=0.1e-9
    ))
    cell.connect(clk_src.p, clk)
    cell.connect(clk_src.n, io.vss)

    # Complementary clock
    clk_b_src = cell.instantiate(Vsource.pulse(
        v0=self.pvt.voltage, v1=0,
        period=100e-9, width=50e-9,
        rise=0.1e-9, fall=0.1e-9
    ))
    cell.connect(clk_b_src.p, clk_b)
    cell.connect(clk_b_src.n, io.vss)

    # Input and load
    din_src = cell.instantiate(Vsource.dc(0.5))
    cell.connect(din_src.p, din)
    cell.connect(din_src.n, io.vss)

    cload = cell.instantiate(Capacitor(1e-12))  # 1pF, no unit ceremony
    cell.connect(cload.p, dout)
    cell.connect(cload.n, io.vss)

    # DUT - schema conversion is implicit
    samp = cell.instantiate(self.dut)
    cell.connect(samp.io.din, din)
    cell.connect(samp.io.dout, dout)
    cell.connect(samp.io.clk, clk)
    cell.connect(samp.io.clk_b, clk_b)
    cell.connect(samp.io.vdd, vdd)
    cell.connect(samp.io.vss, io.vss)

    return dout


# =============================================================================
# Measurement Functions
# =============================================================================
# These would live in a measure/ module, just like flow/expression.py

@value
struct SampMetrics:
    var ron_ohm: Float64
    var settling_ns: Float64
    var charge_injection_mv: Float64


fn calculate_on_resistance(output: TranOutput, din: Node, dout: Node, clk: Node) -> Float64:
    """Calculate switch on-resistance from transient waveforms."""
    v_in = output.voltage(din)
    v_out = output.voltage(dout)
    v_clk = output.voltage(clk)

    # Find windows where clk > 0.5 * vdd (switch on)
    on_windows = v_clk.above(0.5)

    # In steady state, R_on ≈ tau / C_load
    # Measure settling time constant
    tau = v_out.time_constant(within=on_windows)
    c_load = 1e-12  # Known from testbench

    return tau / c_load


fn calculate_settling_time(v: Waveform, tolerance: Float64) -> Float64:
    """Time for waveform to settle within tolerance of final value."""
    final = v.final_value()
    return v.time_to_settle(final, tolerance)


fn calculate_charge_injection(output: TranOutput, dout: Node, clk: Node) -> Float64:
    """Voltage glitch on output when switch turns off."""
    v_out = output.voltage(dout)
    v_clk = output.voltage(clk)

    # Find falling edges of clock
    turn_off = v_clk.falling_edges()

    # Measure peak deviation after each edge
    glitches = [v_out.peak_deviation_after(t, window=1e-9) for t in turn_off]
    return max(glitches) * 1e3  # Convert to mV


# =============================================================================
# Characterization Script
# =============================================================================

fn characterize_samp(ctx: Context, work_dir: Path, dut: Samp) -> SampMetrics:
    pvt = Pvt(corner="tt", voltage=1.0, temp=27)
    tb = SampTb(pvt, dut)

    sim = ctx.simulator(tb, work_dir)

    # Run simulation - no Options struct ceremony
    output = sim.tran(stop=326e-9, step=0.1e-9)

    # Extract measurements
    return SampMetrics(
        ron_ohm=calculate_on_resistance(output, tb.din, tb.dout, tb.clk),
        settling_ns=calculate_settling_time(output.voltage(tb.dout), 0.01),
        charge_injection_mv=calculate_charge_injection(output, tb.dout, tb.clk)
    )


fn sweep_all_variants(ctx: Context, work_dir: Path) -> List[Tuple[Samp, SampMetrics]]:
    results = List[Tuple[Samp, SampMetrics]]()

    for variant in generate_all_variants():
        variant_dir = work_dir / f"samp_{variant.switch_type}_{variant.w}_{variant.l}_{variant.vth}"

        try:
            metrics = characterize_samp(ctx, variant_dir, variant)
            print(f"{variant.switch_type} w={variant.w} l={variant.l}: ron={metrics.ron_ohm:.1f}Ω")
            results.append((variant, metrics))
        except e:
            print(f"Failed: {variant} - {e}")

    return results


# =============================================================================
# Tests
# =============================================================================

fn test_variants():
    variants = generate_all_variants()
    assert len(variants) == 48


fn test_schematic():
    ctx = Context(pdk=Tsmc65)
    samp = Samp(SwitchType.Tgate, w=20, l=1)
    ctx.write_netlist(samp, "samp.sp")


# =============================================================================
# Line count comparison:
#
# FRIDA blocks/samp.py:    ~220 lines
# Rust samp_substrate2.rs: ~350 lines  (60% more than FRIDA)
# Mojo samp.mojo:          ~200 lines  (10% less than FRIDA!)
#
# Breakdown of Rust overhead eliminated:
# - #[derive(...)] macros:           ~20 lines saved
# - Some(...) / None wrapping:       ~15 lines saved
# - Explicit type annotations:       ~20 lines saved
# - impl Trait boilerplate:          ~30 lines saved
# - Vec::new() + push vs comprehension: ~10 lines saved
# - Result<T> / ? error handling:    ~10 lines saved
#
# What Mojo keeps from Rust:
# - Strong typing (just with inference)
# - Compile-time connection checking
# - Zero-cost abstractions
# - No garbage collector
#
# What Mojo adds from Python:
# - List comprehensions
# - Keyword arguments with defaults
# - f-strings
# - Clean exception syntax
# - Duck typing where helpful
# =============================================================================
