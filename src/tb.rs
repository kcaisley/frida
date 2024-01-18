#[cfg(test)]
mod tests {
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