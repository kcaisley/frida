"""One-off: compare a scope capture's spectrum at the interferer frequency from the ADC scan beside it.

The interferer's true frequency f0 comes from the 6/10 MSPS code spectra of the
ADC scan run alongside the capture (aliases unfolded within
6-9 MHz); the capture's amplitude spectral density is then read at f0, 2f0,
and 3f0 against its 6.5-10.5 MHz median floor. Run from the repository root:

    uv run python docs/images/interferer_hunt/hunt_check.py build/test_noise/<stamp>/<step>/fast.h5 <trace> build/scan_adc/<stamp>_adc_sequence_static
"""

import glob
import os
import sys

import numpy as np

from flow.analysis import calc
from flow.analysis.io import read_analysis, read_measurement


def alias(f, fs):
    return abs((f + fs / 2) % fs - fs / 2)


capture, signal, scan = sys.argv[1], sys.argv[2], sys.argv[3]
f0s = []
for f in sorted(glob.glob(scan + "/*_capture.h5"))[:16]:
    m = read_measurement(f)
    fs = m.sample_rate_hz
    if fs < 5e6:
        continue
    x = m.dout.astype(float)
    x -= x.mean()
    fr, p = calc.psd(x, sample_rate=fs, segment_length=8192)
    # 6-9 MHz keeps the aliases unique at 6 and 10 MSPS.
    cand = np.arange(6.0e6, 9.0e6, 1e3)
    sc = np.interp([alias(c, fs) for c in cand], fr, p)
    if sc.max() / np.median(p) > 30:
        f0s.append(cand[np.argmax(sc)])
f0 = np.median(f0s)
print(
    f"{os.path.basename(scan)}: interferer f0 = {f0 / 1e6:.3f} MHz (spread {np.ptp(f0s) / 1e3:.0f} kHz, {len(f0s)} captures)"
)
a = read_analysis(capture)
fr = a.spectrum_frequency_hz
df = fr[1] - fr[0]
asd = a.spectrum_v_per_sqrt_hz[signal]
fl = np.median(asd[(fr > 6.5e6) & (fr < 10.5e6)])
for k in (1, 2, 3):
    b = np.abs(fr - k * f0) < k * 60e3
    i = np.argmax(asd * b)
    print(
        f"  {k}·f0 ≈ {k * f0 / 1e6:.2f} MHz: max {asd[i] * 1e9:.0f} nV/√Hz at {fr[i] / 1e6:.3f} MHz, floor {fl * 1e9:.0f} -> ratio {asd[i] / fl:.1f}, line ≈ {asd[i] * np.sqrt(1.5 * df) * 1e6:.1f} µV"
    )
b = (fr > 6.5e6) & (fr < 10.5e6)
print(
    f"  max ratio anywhere 6.5-10.5 MHz: {(asd[b] / fl).max():.1f}; detection limit ≈ {3 * fl * np.sqrt(1.5 * df) * 1e6:.1f} µV"
)
