// Needs the following system packages:
/// cc, protobuf, protobuf-compiler, sqlite, sqlite-devel


use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};    // Where is this serliaze being used?
use spice::Spice;
use substrate::block::Block;
use substrate::io::{InOut, Io, Output, SchematicType, Signal};
use substrate::schematic::primitives::Resistor;
use substrate::schematic::{CellBuilder, ExportsNestedData, Schematic};


// this is the 'interface' or IO exposed by the voltage divider.
#[derive(Io, Clone, Default, Debug)]
pub struct VdividerIo {
    pub vdd: InOut<Signal>,     // How does this <> syntax work?
    pub vss: InOut<Signal>,
    pub dout: Output<Signal>,
}

// Is this params block the same thing as a block itself; I think not right?
// Imagine a block that doesn't require any params, and is just statically defined?
#[derive(Serialize, Deserialize, Block, Debug, Copy, Clone, Hash, PartialEq, Eq)]
#[substrate(io = "VdividerIo")] // Are all these really necessary?
pub struct Vdivider {   // why do we need to use the pub keyword here?
    /// The top resistance.
    pub r1: Decimal,
    /// The bottom resistance.
    pub r2: Decimal,    
}

// this feels redundant, perhaps it can be integrated into the library?
impl ExportsNestedData for Vdivider {
    type NestedData = ();   // I don't know the type keyword?
}

impl Schematic<Spice> for Vdivider {
    fn schematic(
        &self,
        io: &<<Self as Block>::Io as SchematicType>::Bundle,
        cell: &mut CellBuilder<Spice>,
        ) -> substrate::error::Result<Self::NestedData> {
            let r1 = cell.instantiate(Resistor::new(self.r1));
            let r2 = cell.instantiate(Resistor::new(self.r2));

            cell.connect(io.vdd, r1.io().p);
            cell.connect(io.dout, r1.io().n);
            cell.connect(io.dout, r2.io().p);
            cell.connect(io.vss, r2.io().n);

            Ok(())  // this is a return value? It's part of `core result`?
    }
}

// begin-code-snippet tests
#[cfg(test)]
mod tests {         // why use a module here? So that you can simulate calling the code from an external environment, even if it's in the same file?
    use super::*;
    use rust_decimal_macros::dec;
    use spice::netlist::NetlistOptions;
    use std::path::PathBuf;
    use substrate::context::Context;

    #[test]
    pub fn netlist_vdivider() {
        let ctx = Context::new();
        Spice
            .write_block_netlist_to_file(
                &ctx,
                Vdivider {
                    r1: dec!(100),
                    r2: dec!(200),
                },
                PathBuf::from(concat!(
                    env!("CARGO_MANIFEST_DIR"),
                    "/tests/netlist_vdivider"
                ))
                .join("vdivider.spice"),
                NetlistOptions::default(),
            )
            .expect("failed to netlist vdivider");
    }
}
// end-code-snippet tests