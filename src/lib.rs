use serde::{Deserialize, Serialize};
use spice::Spice;
use substrate::block::Block;
use substrate::io::{InOut, Io, Output, SchematicType, Signal};
use substrate::schematic::primitives::Resistor;
use substrate::schematic::{CellBuilder, ExportsNestedData, Schematic};

#[derive(Io, Clone, Default, Debug)]
pub struct VdividerIo {
    pub vdd: InOut<Signal>,
    pub vss: InOut<Signal>,
    pub dout: Output<Signal>,
}

#[derive(Serialize, Deserialize, Block, Debug, Copy, Clone, Hash, PartialEq, Eq)]
#[substrate(io = "VdividerIo")]
pub struct Vdivider {
    /// The top resistance.
    pub r1: Decimal,
    /// The bottom resistance.
    pub r2: Decimal,
}

impl ExportsNestedData for Vdivider {
    type NestedData = ();
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

        Ok(())
    }
}