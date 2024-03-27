use substrate::io::{InOut, Input, Output, Signal};
use substrate::io::{Io, SchematicType};


#[derive(Io, Clone, Default, Debug)]
pub struct ThreePortMosIo {
    pub d: InOut<Signal>,
    pub g: Input<Signal>,
    pub s: InOut<Signal>,
}

#[derive(Io, Clone, Default, Debug)]
pub struct FourPortMosIo {
    pub d: InOut<Signal>,
    pub g: Input<Signal>,
    pub s: InOut<Signal>,
    pub b: InOut<Signal>,
}

impl From<ThreePortMosIoSchematic> for FourPortMosIoSchematic {     // note how Schematic is created by Derive Io.
    fn from(value: ThreePortMosIoSchematic) -> Self {
        Self {
            d: value.d,         // implementing the From trait also give the Into trait
            g: value.g,
            s: value.s,
            b: value.s,
        }
    }
}



// I can't simple create these at the top level, as they are global...

let three_port_io = ThreePortMosIoSchematic::default();     
let four_port_io = FourPortMosIoSchematic::default();

cell.connect(three_port_io.into(), four_port_io);