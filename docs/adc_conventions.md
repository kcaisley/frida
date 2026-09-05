# ADC stage and code conventions

FRIDA uses conversion order, not numeric bus significance, to name the SAR
path. The 16 capacitor/register stages are `C0` through `C15`: `C0` is the
largest capacitor and the first register updated, while `C15` is the smallest
capacitor and the last register updated. A weight tuple is always stored in
that same C0-first order.

Each conversion produces 17 chronological comparator decisions, `B0` through
`B16`. Decisions `B0` through `B15` determine the updates of `C0` through
`C15`, respectively. `B16` is the extra terminal comparison and does not
switch another capacitor. For ideal decoding their weights are
`[2*C0, 2*C1, ..., 2*C15, 1]`; all 17 decisions contribute to the result.

`DOUT` is the normalized unsigned 12-bit result. Its ordinary binary digits are
`D0` through `D11`, with `D0` the least-significant digit and `D11` the
most-significant digit. `DOUT` is not the slice `B0..B11`: it is the weighted
and normalized result of `B0..B16`.

The unmirrored CDAC is placed small-to-large from local left to right, so its
physical group order is `C15` through `C0`. The complementary branch uses an
MY transform, reversing that visual order. Placement order never changes the
electrical stage names.

The fabricated FRIDA-1 digital macro predates this convention and is also the
digital macro in the current FRIDA-2 template. Its physical bus bit 15 is
chronological stage C0 and its physical bit 0 is C15. That reversal is allowed
only at an explicitly named fabricated-macro boundary in simulation, waveform
mapping, historical PEX parsing, or hardware SPI packing. New generators and
their public parameters, ports, manifests, reports, and analysis arrays are
C0-first. A descending textual bus declaration such as `[15:0]` only declares
the packed bus and does not redefine stage order.
