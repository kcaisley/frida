# SpiceServer Remote Simulation Notes

This document captures the current remote `spice_server` setup used with FRIDA
`--sim-server`, including known issues we hit and the command sequences that
are currently working.

## Scope

- Server host: `jupiter` (RHEL9/AlmaLinux 9)
- Client host: `lt177` (runs `pytest` in `frida`)
- Server process: `~/libs/spice_server/build/spice_server`

## Checkpoint Summary

- `spice_server` builds and runs on `jupiter`.
- Spectre is detected by the server.
- gRPC connectivity from client to `jupiter:50051` is open.
- Embedded netlisting now writes `main.scs`.
- Current simulation blocker is Spectre parsing of raw SPICE literal content
  emitted by FRIDA testbenches (`hs.Literal(...)`).

## Issues Encountered

### Build/ Dependency Issues

- `gRPCConfig.cmake` not found.
  - Fix: pass `-DgRPC_DIR=...` explicitly.
- `glogConfig.cmake` not found on some RHEL/EPEL installs.
  - Fix: install `glog-devel` if available, otherwise build `glog` locally and
    pass `-Dglog_DIR=...`.
- Submodule checkout not aligned with fork/ branch.
  - Fix: update `spice_server` submodule pointer to `kcaisley/Vlsir` `spectre`.

### Runtime/ Environment Issues

- Embedded Python failed importing `vlsir`/ `google.protobuf`.
  - Fix: use a local `spice_server/.venv`, install required Python deps, export
    `PYTHONPATH`, and pass `--python_vlsir`/ `--python_vlsirtools`.
- Client import errors for `spice_simulator_pb2`.
  - Fix: generate protobuf stubs in `~/libs/spice_server/example_client`.
- Connectivity failures (`DNS`, `No route`, `Connection refused`).
  - Fix: use IP address directly, open firewall port `50051/tcp`, ensure server
    is running.

### Current Functional Blocker

- Spectre error `SFE-678` from statements not in Spectre format.
  - Root cause: FRIDA adds raw SPICE literals (`hs.Literal(...)`) which are not
    wrapped in `simulator lang=spice` when netlisted for Spectre.
  - This is the current non-infrastructure failure.

## Server Setup (RHEL9/ AlmaLinux 9)

### System Dependencies

```bash
sudo dnf install -y epel-release
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --set-enabled crb
sudo dnf install -y gcc gcc-c++ make cmake pkgconf-pkg-config
sudo dnf install -y glog-devel gflags-devel
sudo dnf install -y protobuf protobuf-devel protobuf-compiler
sudo dnf install -y grpc grpc-devel re2-devel c-ares-devel openssl-devel
sudo dnf install -y python3.12 python3.12-devel
```

If `glogConfig.cmake` is unavailable, build `glog` locally:

```bash
cd ~/libs
git clone --depth 1 --branch v0.7.1 https://github.com/google/glog.git
cmake -S ~/libs/glog -B ~/libs/glog/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DCMAKE_INSTALL_PREFIX=$HOME/.local
cmake --build ~/libs/glog/build -j
cmake --install ~/libs/glog/build
```

### Clone and Build

```bash
mkdir -p ~/libs
git clone --recurse-submodules https://github.com/kcaisley/spice_server.git ~/libs/spice_server
cd ~/libs/spice_server
```

Configure and build:

```bash
GLOG_DIR=$HOME/.local/lib64/cmake/glog; test -f "$GLOG_DIR/glog-config.cmake" || GLOG_DIR=$HOME/.local/lib/cmake/glog
cmake -S . -B build -DgRPC_DIR=/usr/lib64/cmake/grpc -Dglog_DIR=$GLOG_DIR
cmake --build build -j
```

## Python Runtime for Embedded Netlisting

Use a project-local venv in `spice_server`:

```bash
cd ~/libs/spice_server
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install protobuf
uv pip install -e vlsir_repo/bindings/python
uv pip install -e vlsir_repo/VlsirTools
```

Sanity check:

```bash
python -c "import google.protobuf, vlsir, vlsirtools; print('python deps ok')"
```

## Start Server (Working Command Set)

```bash
cd ~/libs/spice_server
source .venv/bin/activate
source /eda/local/scripts/cadence_2024-25.sh
export PYTHONNOUSERSITE=1
VLSIR=$HOME/libs/spice_server/vlsir_repo/bindings/python
VLSIRTOOLS=$HOME/libs/spice_server/vlsir_repo/VlsirTools
SITEPKG=$HOME/libs/spice_server/.venv/lib/python3.12/site-packages
export PYTHONPATH="$VLSIR:$VLSIRTOOLS:$SITEPKG"
./build/spice_server --port=50051 --python_vlsir="$VLSIR" --python_vlsirtools="$VLSIRTOOLS"
```

## Client-Side Setup (lt177)

Generate SpiceServer Python stubs once:

```bash
cd ~/libs/spice_server/example_client
source ~/frida/.venv/bin/activate
./generate_protobufs.sh
```

Run a single FRIDA simulation test against remote server:

```bash
cd ~/frida
source .venv/bin/activate
pytest flow/adc/test_adc.py::test_adc_flow --flow=simulate --simulator=spectre --sim-server=131.220.165.50:50051 -q -x --tb=short
```

## Connectivity Checks

From client:

```bash
nc -vz 131.220.165.50 50051
```

On server:

```bash
ss -ltnp | rg 50051
```

If using host firewall:

```bash
sudo firewall-cmd --permanent --add-port=50051/tcp
sudo firewall-cmd --reload
```

## SimResult Support Analysis

### SpiceServer Service (Current State)

- The `spice_server` RPC contract does not return `vlsir.spice.SimResult`.
- `RunSimulation` returns a stream of `SimulationResponse` messages:
  - `output` (text chunks),
  - `stream_type` (`STDOUT` or `STDERR`),
  - `exit_code` (final message),
  - `done` (final-message marker).
- In implementation, the server:
  - launches simulator subprocesses,
  - streams subprocess stdout/stderr,
  - sends final exit code,
  - does not parse `.raw`/ CSV into structured analysis results.

Code references:
- `~/libs/spice_server/proto/spice_simulator.proto`
- `~/libs/spice_server/src/simulator_service.cc`
- `~/libs/spice_server/src/simulator_manager.cc`

### VLSIR + VlsirTools Layer (Intended/Implemented SimResult Path)

- The VLSIR `spice.proto` schema defines `service Spice` with:
  - `rpc Sim(SimInput) returns (SimResult)`.
- `SimResult` is a structured list of `AnalysisResult` entries.
- VlsirTools already implements returning structured results as either:
  - Python `sim_data.SimResult`, or
  - protobuf `vlsir.spice.SimResult` via `ResultFormat.VLSIR_PROTO`.
- Tests in VlsirTools explicitly assert protobuf `SimResult` return.

Code references:
- `~/libs/Vlsir/protos/spice.proto`
- `~/libs/spice_server/vlsir_repo/VlsirTools/vlsirtools/spice/spice.py`
- `~/libs/spice_server/vlsir_repo/VlsirTools/vlsirtools/spice/base.py`
- `~/libs/spice_server/vlsir_repo/VlsirTools/vlsirtools/spice/sim_data.py`
- `~/libs/spice_server/vlsir_repo/VlsirTools/tests/test_vlsirtools.py`

### Practical Conclusion

- Input-side VLSIR is integrated in `spice_server` (`vlsir.spice.SimInput`).
- Result-side VLSIR (`vlsir.spice.SimResult`) is not yet exposed by the
  `spice_server` gRPC API.
- Current `spice_server` behavior is log-stream transport, not structured
  simulation-data transport.

## LOC Snapshot (spice_server)

Measured with `cloc`.

- Full checked-out repository (`~/libs/spice_server`):
  - `734,812` code lines
  - Includes vendored `vlsir_repo`, local build output, and virtualenv content.
- Core repo excluding vendored/build/venv:
  - Command: `cloc --exclude-dir=vlsir_repo,build,.venv ~/libs/spice_server`
  - `2,769` code lines.
- Core server implementation only:
  - Command: `cloc ~/libs/spice_server/src ~/libs/spice_server/proto`
  - `848` code lines total
  - `751` C++
  - `40` C/C++ headers
  - `57` Protocol Buffers.
