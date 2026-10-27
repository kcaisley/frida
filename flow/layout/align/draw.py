"""Draw one of a generated ALIGN PDK's generators to GDS, in ALIGN's own Python (``run.draw`` starts
it): ``<generator>().<method>(**arguments)`` of the PDK package, written as the top cell ``top`` by
ALIGN's writer (cell_fabric's ``writeGDS``).

    <ALIGN python> draw.py <spec.json>   # {"pdk_dir", "generator", "method", "arguments", "gds", "top"}
"""

import json
import sys
from pathlib import Path

spec = json.loads(Path(sys.argv[1]).read_text())
pdk_dir = Path(spec["pdk_dir"])
sys.path.insert(0, str(pdk_dir.parent))  # ALIGN imports the PDK directory as a package named after it
package = __import__(pdk_dir.name)
canvas = getattr(package, spec["generator"])()
getattr(canvas, spec["method"])(**spec["arguments"])
with open(spec["gds"], "wb") as stream:
    canvas.writeGDS(stream, macro_name=spec["top"])
