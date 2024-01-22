use serde::{Deserialize, Serialize};    // not sure?
use sky130pdk::mos::{Nfet01v8, Pfet01v8};
use sky130pdk::Sky130Pdk;
use substrate::block::Block;
use substrate::io::{InOut, Input, Output, Signal};
use substrate::io::{Io, SchematicType};
use substrate::schematic::{CellBuilder, ExportsNestedData, Schematic};

