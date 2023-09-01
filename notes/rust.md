

`cargo install` is for an end user. It grabs a bunch of source for probject only, and compiles them to binaries, and puts them in `$USER/.cargo/bin/`. It doesn't add them as a dependencies to any project. Packages need to be on `crates.io` for this to work (?).

Instead, to add a project dependency as a developer, add/remove from your project's Cargo.toml. `cargo add` , `cargo rm` , just edit the `.toml` file. Then run `cargo build` to automaticall fetch all dependencies and compile them. This manifest support registries (crates.io) and source git repositories (github.com)

Cargo clean just removes `target` dir, which contains the build artifacts


# Compiling substrate
Needed to `dnf install protobuf-compiler`

```
error: failed to run custom build command for `cache v0.3.1 (/users/kcaisley/core/substrate2/libs/cache)`

Caused by:
  process didn't exit successfully: `/users/kcaisley/core/substrate2/target/debug/build/cache-8addd479e6c18028/build-script-build` (exit status: 101)
  --- stdout
  cargo:rerun-if-changed=proto/local.proto
  cargo:rerun-if-changed=proto/remote.proto
  cargo:rerun-if-changed=proto/

  --- stderr
  thread 'main' panicked at 'Could not find `protoc` installation and this build crate cannot proceed without
      this knowledge. If `protoc` is installed and this crate had trouble finding
      it, you can set the `PROTOC` environment variable with the specific path to your
      installed `protoc` binary.If you're on debian, try `apt-get install protobuf-compiler` or download it from https://github.com/protocolbuffers/protobuf/releases

  For more information: https://docs.rs/prost-build/#sourcing-protoc
  ', /users/kcaisley/.cargo/registry/src/index.crates.io-6f17d22bba15001f/prost-build-0.11.9/src/lib.rs:1457:10
  note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
warning: build failed, waiting for other jobs to finish...
error: Recipe `check` failed on line 8 with exit code 101
```

# Testing substrate
Needed to `dnf install sqlite sqlite-devel`

```
  = note: /usr/bin/ld: cannot find -lsqlite3: No such file or directory
          collect2: error: ld returned 1 exit status
          

error: could not compile `sky130_inverter` (lib test) due to previous error
error: Recipe `test` failed on line 6 with exit code 101
error: Recipe `test-examples` failed on line 35 with exit code 101
```

Looks like I also need the skywater pdk.

```
running 35 tests
test derive::io::tests::named_struct_io_implements_io ... ok
test derive::io::tests::generic_io_implements_io ... ok
test derive::io::tests::tuple_io_implements_io ... ok
test gds::test_gds_import_nonexistent_layer ... FAILED
test gds::test_gds_import_invalid_units ... FAILED
test hard_macro::export_hard_macro ... FAILED
test gds::test_gds_reexport ... FAILED
test gds::test_gds_import ... FAILED
test hard_macro::export_hard_macro_gds ... FAILED
test layout::transform_point_enum ... ok
test hard_macro::export_inline_hard_macro ... FAILED
test layout::translate_two_point_group ... ok
test netlist::vdivider_blackbox_is_valid ... ok
test netlist::vdivider_is_valid ... ok
test netlist::netlist_spectre_vdivider ... ok
test netlist::netlist_spice_vdivider_blackbox ... ok
test netlist::netlist_spice_vdivider ... ok
test pdk::test_pdk_layers ... ok
test pdk::export_nmos_a ... ok
test schematic::nested_io_naming ... ok
test layout::grid_tiler_works_with_various_spans ... ok
test schematic::error_propagation_works ... ok
test scir::merge_scir_libraries ... ok
test schematic::can_generate_vdivider_schematic ... ok
test schematic::can_generate_flattened_vdivider_schematic ... ok
test cache::caching_works ... ok
test shared::array_short::tests::panics_when_shorting_ios - should panic ... ok
test sim::ngspice::ngspice_can_save_voltages_and_currents ... FAILED
test schematic::can_generate_flattened_vdivider_array_schematic ... ok
test schematic::nested_node_naming ... ok
test layout::nested_transform_views_work ... ok
test schematic::internal_signal_names_preserved ... ok
test layout::layout_generation_and_data_propagation_work ... ok
test layout::cell_builder_supports_bbox ... ok
test netlist::netlist_spice_vdivider_is_repeatable ... ok

failures:

---- gds::test_gds_import_nonexistent_layer stdout ----
thread 'gds::test_gds_import_nonexistent_layer' panicked at 'the SKY130_OPEN_PDK_ROOT environment variable must be set: NotPresent', tests/src/shared/pdk/mod.rs:163:10
```



```
git clone https://github.com/google/skywater-pdk.git
SUBMODULE_VERSION=latest make submodules -j3 || make submodules -j1 # Expect a large download! ~7GB at time of writing.
make timing # Regenerate liberty files
```

And now:
```
+ set -e
+ ngspice -b -r /users/kcaisley/core/substrate2/tests/build/ngspice_can_save_voltages_and_currents/sim/data.raw /users/kcaisley/core/substrate2/tests/build/ngspice_can_save_voltages_and_currents/sim/netlist.spice
test sim::ngspice::ngspice_can_save_voltages_and_currents ... FAILED
```

Now, running this:

cargo test --locked -p config --lib

It works?

```
running 2 tests
test tests::test_raw_config ... ok
test tests::test_config ... ok
```

Ah, I renamed the directory to code, but it's still referencing core.
