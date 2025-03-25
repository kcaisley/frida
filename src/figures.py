from svg_schematic import Schematic, Resistor, Capacitor, Inductor, Wire
from inform import Error, error, os_error

try:
    with Schematic(filename='rlc.svg'):
        r = Resistor(name='R', orient='v')
        c = Capacitor(W=r.E, name='C', orient='v')
        l = Inductor(W=c.E, name='L', orient='v|')
        Wire([r.p, l.p])
        Wire([r.n, l.n])
except Error as e:
    e.report()
except OSError as e:
    error(os_error(e))
