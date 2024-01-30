use serde::{Deserialize, Serialize};    // not sure?
use sky130pdk::mos::{Nfet01v8, Pfet01v8};
use sky130pdk::Sky130Pdk;
use substrate::block::Block;
use substrate::io::{InOut, Input, Output, Signal};
use substrate::io::{Io, SchematicType};
use substrate::schematic::{CellBuilder, ExportsNestedData, Schematic};

pub mod tb; // how does this reference thing work?

// What are all the derives here?
#[derive(Io, Clone, Default, Debug)]
pub struct InverterIo {
    pub vdd: InOut<Signal>,
    pub vss: InOut<Signal>,
    pub din: Input<Signal>,
    pub dout: Output<Signal>,
}

// structs are how new types can be defined
// The directionals above are structs around structs, essentially
// just giving types to dout.

// Given attributes to struct mean it implements them?
#[derive(Serialize, Deserialize, Block, Debug, Copy, Clone, Hash, PartialEq, Eq)]
#[substrate(io = "InverterIo")]
pub struct Inverter {
    // NMOS width
    pub nw: i64,
    pub pw: i64,
    pub lch: i64,
}

impl ExportsNestedData for Inverter {
    type NestedData = ();
}

// what does a parameterized impl do again?
// we're dictating how a method 
impl Schematic<Sky130Pdk> for Inverter {
    fn schematic(
            &self,
            io: &<<Self as Block>::Io as SchematicType>::Bundle,
            cell: &mut CellBuilder<Sky130Pdk>,
        ) -> substrate::error::Result<Self::NestedData> {

        let nmos = cell.instantiate(Nfet01v8::new((self.nw, self.lch)));
        cell.connect(io.dout, nmos.io().d);
        cell.connect(io.din, nmos.io().g);
        cell.connect(io.vss, nmos.io().s);
        cell.connect(io.vss, nmos.io().b);
        
        let pmos = cell.instantiate(Pfet01v8::new((self.pw, self.lch)));
        cell.connect(io.dout, pmos.io().d);
        cell.connect(io.din, pmos.io().g);
        cell.connect(io.vdd, pmos.io().s);
        cell.connect(io.vdd, pmos.io().b);

        Ok(())  // code without semicolon produces return value.
    }
}
