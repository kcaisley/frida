use super::Inverter;
// what does super mean here?

use ngspice::tran::Tran;
use ngspice::Ngspice;
use rust_decimal::prelude::ToPrimitive;
use rust_decimal_macros::dec;
use serde::{Deserialize, Serialize};
use sky130pdk::corner::Sky130Corner;
use sky130pdk::Sky130Pdk;
use std::path::Path;
use substrate::block::Block;
use substrate::context::{Context, PdkContext};
use substrate::io::{Node, SchematicType, Signal, TestbenchIo};
use substrate::pdk::corner::Pvt;
use substrate::schematic::{Cell, CellBuilder, ExportsNestedData, Schematic};
use substrate::simulation::data::{tran, FromSaved, Save, SaveTb};
use substrate::simulation::waveform::{EdgeDir, TimeWaveform, WaveformRef};
use substrate::simulation::{SimulationContext, Simulator, Testbench};

// creating a testbench is the same as a regular block, except without IO


#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash, Serialize, Deserialize, Block)]   // automatically generate traits (clone, etc) for InverterTb struct, using Derive attribute. 
#[substrate(io = "TestbenchIo")]    // like above, this in attribute macro. In the context of Substrate, all TBs must have this attribute. 
pub struct InverterTb {
    pvt: Pvt<Sky130Corner>,    // 3-tuple of corner, V, and temp. Also it's a 'generic type', as it takes a parameter
    dut: Inverter,          // a struct is a compound type
}

impl InverterTb {   // is this an inherent implementation?. No this is a constructor method for instances of 
    #[inline]   // optional hint to the compiler to inline the function at later call sites. Useful for small, frequently called functions like constructors.
    pub fn new(pvt: Pvt<Sky130Corner>, dut: Inverter) -> Self {
        Self { pvt, dut }
    }
}

impl ExportsNestedData for InverterTb{  // why can't this be put in a derive macro?
    type NestedData = Node;
}


// is this impl ever called? I guess it just gives properties to the Testbench
impl Schematic<Ngspice> for InverterTb {
    fn schematic(
        &self,
        io: &<<Self as Block>::Io as SchematicType>::Bundle, //`as` casts one type to another
        cell: &mut CellBuilder<Ngspice>,            // Method on testbench, which 
    ) -> substrate::error::Result<Self::NestedData> {
        
        // cell is a CellBuilder struct, of the Ngspice type
        // notice how all method have a `()` after them, but can sometimes be parameterized for a certain pdk
        let inv = cell.sub_builder::<Sky130Pdk>().instantiate(self.dut);

        let vdd = cell.signal("vdd", Signal);
        let dout = cell.signal("dout", Signal);

        let vddsrc = cell.instantiate(ngspice::blocks::Vsource::dc(self.pvt.voltage));
        cell.connect(vddsrc.io().p, vdd);
        cell.connect(vddsrc.io().n,io.vss);

        let vin = cell.instantiate(ngspice::blocks::Vsource::pulse(ngspice::blocks::Pulse {
            val0: 0.into(),
            val1: self.pvt.voltage,
            delay: Some(dec!(0.1e-9)),
            width: Some(dec!(0.1e-9)),
            fall: Some(dec!(1e-12)),
            rise: Some(dec!(1e-12)),
            period: None,
            num_pulses: Some(dec!(1)),
        }));
        
        cell.connect(inv.io().din, vin.io().p);
        cell.connect(vin.io().n, io.vss);

        cell.connect(inv.io().vdd, vdd);
        cell.connect(inv.io().vss, io.vss);
        cell.connect(inv.io().dout, dout);

        Ok(dout)    // note how the return type is the node to probe.
    }

}

// next, we want to run our testbench, to test the 20-80% rise and fall time

// Debug allows for fmt print debugging, Clone is deep copying, De/Serialize is for transmission or storage, FromSaved not in stdlib
#[derive(Debug, Clone, Serialize, Deserialize, FromSaved)]   
pub struct Vout {       //... a struct is a compound type ...
    t: tran::Time,      // this struct is a container for output data
    v: tran::Voltage,
}

impl SaveTb<Ngspice, ngspice::tran::Tran, Vout> for InverterTb {
    fn save_tb(
        ctx: &SimulationContext<Ngspice>,   // simulation context
        cell: &Cell<Self>,  
        opts: &mut <Ngspice as Simulator>::Options,
    ) -> <Vout as FromSaved<Ngspice, Tran>>::SavedKey {
        VoutSavedKey {                                      // this is the return value; as note the lack of semicolon
            t: tran::Time::save(ctx, (), opts),     // marks the time data for saving
            v: tran::Voltage::save(ctx, cell.data(), opts),     // marks the voltage data for saving.
        }
    }
}

// is this going to be automatically executed? Or do I need to myself manually?
impl Testbench<Ngspice> for InverterTb {
    type Output = Vout; // defines an alias for Vout type
    fn run(&self, sim: substrate::simulation::SimController<Ngspice, Self>) -> Self::Output {
        let mut opts = ngspice::Options::default();
        sim.set_option(self.pvt.corner, &mut opts);
        sim.simulate(
            opts,
            ngspice::tran::Tran {
                stop: dec!(2e-9),
                step: dec!(1e-11),
                ..Default::default()
            },
        )
        .expect("failed to run simulation")
    }
}



/// Designs an inverter for balanced pull-up and pull-down times.
///
/// The NMOS width is kept constant; the PMOS width is swept over
/// the given range.
pub struct InverterDesign {
    /// The fixed NMOS width.
    pub nw: i64,
    /// The set of PMOS widths to sweep.
    pub pw: Vec<i64>,
    /// The transistor channel length.
    pub lch: i64,
}

impl InverterDesign {
    pub fn run<S: Simulator>(
        &self,
        ctx: &mut PdkContext<Sky130Pdk>,
        work_dir: impl AsRef<Path>,
    ) -> Inverter
    where
        InverterTb: Testbench<S, Output = Vout>,
    {
        let work_dir = work_dir.as_ref();
        let pvt = Pvt::new(Sky130Corner::Tt, dec!(1.8), dec!(25));

        let mut opt = None;
        for pw in self.pw.iter().copied() {
            let dut = Inverter {
                nw: self.nw,
                pw,
                lch: self.lch,
            };
            let tb = InverterTb::new(pvt, dut);
            let output = ctx
                .simulate(tb, work_dir.join(format!("pw{pw}")))
                .expect("failed to run simulation");

            let vout = WaveformRef::new(&output.t, &output.v);
            let mut trans = vout.transitions(
                0.2 * pvt.voltage.to_f64().unwrap(),
                0.8 * pvt.voltage.to_f64().unwrap(),
            );
            // The input waveform has a low -> high, then a high -> low transition.
            // So the first transition of the inverter output is high -> low.
            // The duration of this transition is the inverter fall time.
            let falling_transition = trans.next().unwrap();
            assert_eq!(falling_transition.dir(), EdgeDir::Falling);
            let tf = falling_transition.duration();
            let rising_transition = trans.next().unwrap();
            assert_eq!(rising_transition.dir(), EdgeDir::Rising);
            let tr = rising_transition.duration();

            println!("Simulating with pw = {pw} gave tf = {}, tr = {}", tf, tr);
            let diff = (tr - tf).abs();
            if let Some((pdiff, _)) = opt {
                if diff < pdiff {
                    opt = Some((diff, dut));
                }
            } else {
                opt = Some((diff, dut));
            }
        }

        opt.unwrap().1
    }
}

/// Create a new Substrate context for the SKY130 open PDK.
///
/// Sets the PDK root to the value of the `SKY130_OPEN_PDK_ROOT`
/// environment variable and installs Spectre with default configuration.
///
/// # Panics
///
/// Panics if the `SKY130_OPEN_PDK_ROOT` environment variable is not set,
/// or if the value of that variable is not a valid UTF-8 string.
pub fn sky130_open_ctx() -> PdkContext<Sky130Pdk> {
    let pdk_root = std::env::var("SKY130_OPEN_PDK_ROOT")
        .expect("the SKY130_OPEN_PDK_ROOT environment variable must be set");
    Context::builder()
        .install(Ngspice::default())
        .install(Sky130Pdk::open(pdk_root))
        .build()
        .with_pdk() 
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    pub fn design_inverter_ngspice() {
        let work_dir = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/design_inverter_ngspice");
        let mut ctx = sky130_open_ctx();
        let script = InverterDesign {
            nw: 1_200,
            pw: (1_200..=5_000).step_by(200).collect(),
            lch: 150,
        };

        let inv = script.run::<Ngspice>(&mut ctx, work_dir);
        println!("Designed inverter:\n{:#?}", inv);
    }
}