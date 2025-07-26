import numpy as np
from spicelib import Trace, RawWrite

LW = RawWrite()

tx = Trace('time', np.arange(0.0, 3e-3, 997E-11))
vy = Trace('N001', np.sin(2 * np.pi * tx.data * 10000))
vz = Trace('N002', np.cos(2 * np.pi * tx.data * 9970))

LW.add_trace(tx)
LW.add_trace(vy)
LW.add_trace(vz)

LW.save("test_sincos.raw")