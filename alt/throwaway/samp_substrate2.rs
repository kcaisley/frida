//! Sampling Switch in Substrate2
//!
//! This is a direct translation of blocks/samp.py from the FRIDA project.
//! It demonstrates how the Python declarative style maps to Substrate2's
//! Rust-based approach.
//!
//! Original FRIDA block: ~70 lines (subckt + gen_topo_subckt)
//! This Substrate2 version: ~200 lines (more verbose, but type-safe)

use substrate::block::Block;
use substrate::context::Context;
use substrate::error::Result;
use substrate::schematic::{CellBuilder, Schematic};
use substrate::types::schematic::IoNodeBundle;
use substrate::types::{InOut, Input, Io, Output, Signal};

// =============================================================================
// IO Definition
// =============================================================================
// FRIDA equivalent:
//   ports = {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"}

#[derive(Io, Clone, Default, Debug)]
pub struct SampIo {
    pub din: Input<Signal>,
    pub dout: Output<Signal>,
    pub clk: Input<Signal>,
    pub clk_b: Input<Signal>,
    pub vdd: InOut<Signal>,
    pub vss: InOut<Signal>,
}

// =============================================================================
// Topology and Device Parameter Enums
// =============================================================================
// FRIDA equivalent:
//   topo_params = {"switch_type": ["nmos", "pmos", "tgate"]}
//   inst_params = [{"instances": {...}, "type": ["lvt", "svt"]}]

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub enum SwitchType {
    Nmos,
    Pmos,
    Tgate,
}

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub enum Vth {
    Lvt,
    Svt,
}

// =============================================================================
// Block Definition
// =============================================================================
// FRIDA equivalent:
//   subckt = {
//       "cellname": "samp",
//       "tech": ["tsmc65", "tsmc28", "tower180"],
//       "topo_params": {"switch_type": ["nmos", "pmos", "tgate"]},
//       "inst_params": [
//           {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": [5, 10, 20, 40], "l": [1, 2]},
//           {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", ...},
//       ],
//   }

#[derive(Block, Debug, Copy, Clone, Hash, PartialEq, Eq)]
#[substrate(io = "SampIo")]
pub struct Samp {
    // Topology parameter
    pub switch_type: SwitchType,
    // Device parameters (from inst_params sweeps)
    pub w: i64,   // Width in nm (values: 5, 10, 20, 40 in min units)
    pub l: i64,   // Length in nm (values: 1, 2 in min units)
    pub vth: Vth, // Threshold voltage type
}

impl Samp {
    pub fn new(switch_type: SwitchType, w: i64, l: i64, vth: Vth) -> Self {
        Self { switch_type, w, l, vth }
    }
}

// =============================================================================
// Schematic Implementation
// =============================================================================
// FRIDA equivalent: gen_topo_subckt(switch_type: str)
//
// Note: In a real implementation, you'd use your PDK's device types.
// This example uses placeholder types to show the structure.

impl Schematic for Samp {
    type Schema = Tsmc65; // Would be generic over Schema for multi-tech
    type NestedData = ();

    fn schematic(
        &self,
        io: &IoNodeBundle<Self>,
        cell: &mut CellBuilder<Self::Schema>,
    ) -> Result<Self::NestedData> {
        match self.switch_type {
            SwitchType::Nmos => {
                // FRIDA equivalent:
                //   instances["MN"] = {
                //       "dev": "nmos",
                //       "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
                //   }
                let mn = cell.instantiate(Nfet::new(self.w, self.l, self.vth));
                cell.connect(io.dout, mn.io().d);
                cell.connect(io.clk, mn.io().g);
                cell.connect(io.din, mn.io().s);
                cell.connect(io.vss, mn.io().b);
            }
            SwitchType::Pmos => {
                // FRIDA equivalent:
                //   instances["MP"] = {
                //       "dev": "pmos",
                //       "pins": {"d": "out", "g": "clk_b", "s": "in", "b": "vdd"},
                //   }
                let mp = cell.instantiate(Pfet::new(self.w, self.l, self.vth));
                cell.connect(io.dout, mp.io().d);
                cell.connect(io.clk_b, mp.io().g);
                cell.connect(io.din, mp.io().s);
                cell.connect(io.vdd, mp.io().b);
            }
            SwitchType::Tgate => {
                // FRIDA equivalent:
                //   instances["MN"] = {"dev": "nmos", "pins": {...}}
                //   instances["MP"] = {"dev": "pmos", "pins": {...}}
                let mn = cell.instantiate(Nfet::new(self.w, self.l, self.vth));
                cell.connect(io.dout, mn.io().d);
                cell.connect(io.clk, mn.io().g);
                cell.connect(io.din, mn.io().s);
                cell.connect(io.vss, mn.io().b);

                let mp = cell.instantiate(Pfet::new(self.w, self.l, self.vth));
                cell.connect(io.dout, mp.io().d);
                cell.connect(io.clk_b, mp.io().g);
                cell.connect(io.din, mp.io().s);
                cell.connect(io.vdd, mp.io().b);
            }
        }
        Ok(())
    }
}

// =============================================================================
// Sweep Generation (replaces automatic cartesian product expansion)
// =============================================================================
// FRIDA does this automatically via topo_params × inst_params × tech.
// In Substrate2, you write explicit iteration.

/// Generate all Samp variants for sweeping.
///
/// FRIDA equivalent: The automatic expansion of:
///   topo_params = {"switch_type": ["nmos", "pmos", "tgate"]}
///   inst_params = [{"w": [5, 10, 20, 40], "l": [1, 2], "type": ["lvt", "svt"]}]
///
/// Total variants: 3 switch_types × 4 widths × 2 lengths × 2 vth = 48 per tech
pub fn generate_all_variants() -> Vec<Samp> {
    let switch_types = [SwitchType::Nmos, SwitchType::Pmos, SwitchType::Tgate];
    let widths = [5, 10, 20, 40];
    let lengths = [1, 2];
    let vths = [Vth::Lvt, Vth::Svt];

    let mut variants = Vec::new();

    for switch_type in switch_types {
        for w in widths {
            for l in lengths {
                for vth in vths {
                    variants.push(Samp::new(switch_type, w, l, vth));
                }
            }
        }
    }

    variants // Returns 48 variants
}

/// Generate variants with filtering (like FRIDA's None,None return for invalid combos)
pub fn generate_filtered_variants() -> Vec<Samp> {
    generate_all_variants()
        .into_iter()
        .filter(|s| {
            // Example filter: skip PMOS with very small width (hypothetical constraint)
            !(s.switch_type == SwitchType::Pmos && s.w < 10)
        })
        .collect()
}

// =============================================================================
// Testbench (simplified example)
// =============================================================================
// FRIDA equivalent: tb = {"instances": {...}, "analyses": {...}}
//
// In Substrate2, testbenches are also blocks with schematics.

use substrate::types::TestbenchIo;
use substrate::simulation::Pvt;

#[derive(Clone, Debug, Hash, PartialEq, Eq, Block)]
#[substrate(io = "TestbenchIo")]
pub struct SampTb {
    pub pvt: Pvt<Tsmc65Corner>,
    pub dut: Samp,
}

impl SampTb {
    pub fn new(pvt: Pvt<Tsmc65Corner>, dut: Samp) -> Self {
        Self { pvt, dut }
    }
}

impl Schematic for SampTb {
    type Schema = Ngspice;
    type NestedData = Node; // Output node for probing

    fn schematic(
        &self,
        io: &IoNodeBundle<Self>,
        cell: &mut CellBuilder<Self::Schema>,
    ) -> Result<Self::NestedData> {
        // Create internal signals
        let vdd = cell.signal("vdd", Signal);
        let clk = cell.signal("clk", Signal);
        let clk_b = cell.signal("clk_b", Signal);
        let din = cell.signal("din", Signal);
        let dout = cell.signal("dout", Signal);

        // Power supply
        // FRIDA: "Vvdd": {"dev": "vsource", "wave": "dc", "params": {"dc": 1.0}}
        let vdd_src = cell.instantiate(Vsource::dc(self.pvt.voltage));
        cell.connect(vdd_src.io().p, vdd);
        cell.connect(vdd_src.io().n, io.vss);

        // Clock source
        // FRIDA: "Vclk": {"wave": "pulse", "params": {"v1": 0, "v2": 1.0, ...}}
        let clk_src = cell.instantiate(Vsource::pulse(Pulse {
            val0: 0.into(),
            val1: self.pvt.voltage,
            delay: Some(dec!(0)),
            width: Some(dec!(50e-9)),
            rise: Some(dec!(0.1e-9)),
            fall: Some(dec!(0.1e-9)),
            period: Some(dec!(100e-9)),
            num_pulses: None,
        }));
        cell.connect(clk_src.io().p, clk);
        cell.connect(clk_src.io().n, io.vss);

        // Complementary clock
        let clk_b_src = cell.instantiate(Vsource::pulse(Pulse {
            val0: self.pvt.voltage,
            val1: 0.into(),
            delay: Some(dec!(0)),
            width: Some(dec!(50e-9)),
            rise: Some(dec!(0.1e-9)),
            fall: Some(dec!(0.1e-9)),
            period: Some(dec!(100e-9)),
            num_pulses: None,
        }));
        cell.connect(clk_b_src.io().p, clk_b);
        cell.connect(clk_b_src.io().n, io.vss);

        // Input source (DC staircase would need PWL - simplified here)
        let din_src = cell.instantiate(Vsource::dc(dec!(0.5)));
        cell.connect(din_src.io().p, din);
        cell.connect(din_src.io().n, io.vss);

        // Load capacitor
        // FRIDA: "Cload": {"dev": "cap", "pins": {...}, "params": {"c": 1e3}}
        let cload = cell.instantiate(Capacitor::new(dec!(1e-12))); // 1pF
        cell.connect(cload.io().p, dout);
        cell.connect(cload.io().n, io.vss);

        // Instantiate DUT
        // FRIDA: "Xdut": {"cell": "samp", "pins": {...}}
        let samp = cell
            .sub_builder::<Tsmc65Schema>()
            .instantiate(ConvertSchema::new(self.dut));
        cell.connect(samp.io().din, din);
        cell.connect(samp.io().dout, dout);
        cell.connect(samp.io().clk, clk);
        cell.connect(samp.io().clk_b, clk_b);
        cell.connect(samp.io().vdd, vdd);
        cell.connect(samp.io().vss, io.vss);

        Ok(dout.into())
    }
}

// =============================================================================
// Simulation and Measurement (design script)
// =============================================================================
// FRIDA equivalent:
//   analyses = {"tran": {"command": "tran(stop=326e-9, ...)"}}
//   measures = {
//       "ron_ohm": {"expression": "m.samp_on_resistance(...)"},
//       "settling_ns": {"expression": "m.samp_settling_time(...)"},
//       "charge_injection_mV": {"expression": "m.samp_charge_injection(...)"},
//   }

pub struct SampMetrics {
    pub ron_ohm: f64,
    pub settling_ns: f64,
    pub charge_injection_mv: f64,
}

pub fn characterize_samp(ctx: &mut Context, work_dir: &Path, dut: Samp) -> Result<SampMetrics> {
    let pvt = Pvt::new(Tsmc65Corner::Tt, dec!(1.0), dec!(27));
    let tb = SampTb::new(pvt, dut);

    let sim = ctx.get_sim_controller(tb, work_dir)?;
    let mut opts = ngspice::Options::default();
    sim.set_option(pvt.corner, &mut opts);

    // Run transient simulation
    // FRIDA: "command": "tran(stop=326e-9, errpreset='conservative')"
    let output = sim.simulate(
        opts,
        ngspice::tran::Tran {
            stop: dec!(326e-9),
            step: dec!(1e-10),
            ..Default::default()
        },
    )?;

    // Extract measurements from waveforms
    // FRIDA: These would call m.samp_on_resistance(), etc.
    let dout_node = output.data();
    let vout = output.get_voltage(dout_node);

    // Simplified measurement extraction (real impl would be more complex)
    let ron_ohm = calculate_on_resistance(&output);
    let settling_ns = calculate_settling_time(&vout, 0.01);
    let charge_injection_mv = calculate_charge_injection(&output);

    Ok(SampMetrics {
        ron_ohm,
        settling_ns,
        charge_injection_mv,
    })
}

// =============================================================================
// Full Sweep Characterization
// =============================================================================
// This replaces the automatic flow: make sim cell=samp mode=all

pub fn sweep_all_samp_variants(ctx: &mut Context, work_dir: &Path) -> Vec<(Samp, SampMetrics)> {
    let mut results = Vec::new();

    for variant in generate_all_variants() {
        let variant_dir = work_dir.join(format!(
            "samp_{:?}_w{}_l{}_{:?}",
            variant.switch_type, variant.w, variant.l, variant.vth
        ));

        match characterize_samp(ctx, &variant_dir, variant) {
            Ok(metrics) => {
                println!(
                    "{:?} w={} l={} {:?}: ron={:.1}Ω settling={:.2}ns",
                    variant.switch_type, variant.w, variant.l, variant.vth,
                    metrics.ron_ohm, metrics.settling_ns
                );
                results.push((variant, metrics));
            }
            Err(e) => {
                eprintln!("Failed to simulate {:?}: {}", variant, e);
            }
        }
    }

    results
}

// =============================================================================
// Test (equivalent to: cargo test design_samp -- --show-output)
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_variants() {
        let variants = generate_all_variants();
        // 3 switch_types × 4 widths × 2 lengths × 2 vth = 48
        assert_eq!(variants.len(), 48);
    }

    #[test]
    fn test_samp_schematic() {
        let ctx = tsmc65_ctx(); // Would create context with PDK
        let samp = Samp::new(SwitchType::Tgate, 20, 1, Vth::Lvt);

        // Generate and export netlist
        let work_dir = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/samp"));
        ctx.write_schematic(samp, &work_dir.join("samp.sp")).unwrap();
    }

    #[test]
    fn test_full_sweep() {
        let mut ctx = tsmc65_ctx();
        let work_dir = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/samp_sweep"));
        let results = sweep_all_samp_variants(&mut ctx, &work_dir);

        // Find best variant (lowest ron)
        let best = results
            .iter()
            .min_by(|a, b| a.1.ron_ohm.partial_cmp(&b.1.ron_ohm).unwrap())
            .unwrap();

        println!("Best variant: {:?} with ron={:.1}Ω", best.0, best.1.ron_ohm);
    }
}

// =============================================================================
// Placeholder types (would come from PDK plugin in real implementation)
// =============================================================================
// These are stubs to make the example compile-ready in concept.
// Real implementation would import from sky130, tsmc65, etc.

mod placeholder {
    pub struct Tsmc65;
    pub struct Tsmc65Schema;
    pub struct Tsmc65Corner;
    pub struct Ngspice;
    pub struct Node;
    pub struct Nfet { w: i64, l: i64, vth: super::Vth }
    pub struct Pfet { w: i64, l: i64, vth: super::Vth }
    pub struct Vsource;
    pub struct Pulse { /* fields */ }
    pub struct Capacitor;

    impl Nfet {
        pub fn new(w: i64, l: i64, vth: super::Vth) -> Self { Self { w, l, vth } }
    }
    impl Pfet {
        pub fn new(w: i64, l: i64, vth: super::Vth) -> Self { Self { w, l, vth } }
    }
}

// =============================================================================
// Line count comparison:
//
// FRIDA blocks/samp.py (subckt + tb + analyses + measures): ~220 lines
// This Substrate2 version (equivalent functionality):       ~350 lines
//
// The Substrate2 version is ~60% longer, but provides:
// - Compile-time type checking of all connections
// - IDE autocomplete for ports and parameters
// - Refactoring safety (rename a port, compiler finds all uses)
// - No runtime "KeyError" or typo bugs in port names
//
// The cost is:
// - More boilerplate (struct definitions, trait impls)
// - Explicit loops instead of automatic cartesian product
// - Learning Rust
// =============================================================================
