"""The single-instance page's statistics (``flow.web.page``): a netlist's, DRC's and a Calibre LVS
report's, on made-up inputs."""

import json

from flow.web import page

NETLIST = """\
* a made-up block
.subckt inv A Y VDD VSS
mn Y A VSS VSS nmos_x w=240n l=60n nf=1
mp Y A VDD VDD pmos_x w=240n l=60n nf=1
.ends inv
.subckt top IN OUT VDD VSS
Xa IN mid VDD VSS inv
Xb mid OUT VDD VSS inv
Xc OUT VSS cap_cell length=4230
C1 OUT VSS 1f
.ends top
"""

REPORT = """\
NUMBERS OF OBJECTS AFTER TRANSFORMATION
---------------------------------------

                Layout    Source         Component Type
                ------    ------         --------------
 Ports:              4         4

 Nets:              40        41    *

 Instances:         26        26         cap_a (3 pins)
                    18        18         _invx2v (4 pins)
                ------    ------
 Total Inst:        44        44


**************************************************************************************************************
                                   INCORRECT NETS

DISC#  LAYOUT NAME                                               SOURCE NAME
**************************************************************************************************************

  1    Net 69                                                    XTOP/a
--------------------------------------------------------------------------------------------------------------
  2    Net 23                                                    ** missing net **

**************************************************************************************************************
                               INFORMATION AND WARNINGS
"""


def test_netlist_stats():
    stats = page.netlist_stats(NETLIST)
    assert stats["top"] == "top"
    assert (stats["ports"], stats["instances"], stats["subcircuits"]) == (4, 4, 2)
    assert stats["nets"] == 5  # in, out, mid, vdd, vss
    assert stats["leaves"] == {"MOS nmos_x": 2, "MOS pmos_x": 2, "capacitor": 1, "cell cap_cell": 1}


def test_calibre_lvs():
    found = page.calibre_lvs(REPORT)
    assert found["rows"] == [
        ["Ports", 4, 4],
        ["Nets", 40, 41],
        ["Instances: cap_a (3 pins)", 26, 26],
        ["Instances: _invx2v (4 pins)", 18, 18],
        ["Total Inst", 44, 44],
    ]
    assert found["wrong"] == {"nets": 2, "instances": 0}


def test_drc_stats(tmp_path):
    assert page.drc_stats(tmp_path) is None
    (tmp_path / "drc_violations.json").write_text(
        json.dumps({"checker": "x", "violations": {"A.1": 1, "B.2": 3}, "waived": {}})
    )
    assert page.drc_stats(tmp_path) == {"checker": "x", "rules": {"B.2": 3, "A.1": 1}, "total": 4, "waived": {}}
