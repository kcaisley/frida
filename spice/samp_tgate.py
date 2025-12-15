from src.run_analysis import read_traces, quantize, diff, comm, write_analysis
import numpy as np


def analyze(raw, netlist, raw_file):
    time, vin, vout, vclk, vclkb, vdda, vssa = read_traces(raw)

    qvclk = quantize(vclk, bits=1, max=1.2, min=0)
    vdiff = diff(vin, vout)
    vcomm = comm(vin, vout)

    max_error_V = float(np.max(np.abs(vdiff)))
    rms_error_V = float(np.sqrt(np.mean(vdiff**2)))

    write_analysis(raw_file, time, vin, vout, vclk, vclkb, vdda, vssa, qvclk, vdiff, vcomm, max_error_V, rms_error_V)