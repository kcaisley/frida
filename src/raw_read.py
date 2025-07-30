import spicelib

# Load the file using spicelib
raw1 = spicelib.RawRead("build/raw/fourbitadder.ngbin", dialect="ngspice")

T1 = raw1.get_trace('time')
N1 = raw1.get_trace('v(1)')

traceT1 = spicelib.Trace('time', T1.data)
traceN1 = spicelib.Trace('v(1)', N1.data)

raw2 = spicelib.RawWrite(encoding="utf_8", fastacces=False)
raw2.add_trace(traceT1)
raw2.add_trace(traceN1)
raw2.save("build/raw/fourbitadder_rewrite.ngbin")

raw3 = spicelib.RawRead("build/raw/fourbitadder_rewrite.ngbin")

print("done")