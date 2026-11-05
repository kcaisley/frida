# ruff: noqa  -- ALIGN style: ALIGN asks the PDK package for these by name
"""The PDK's device models for ALIGN (its ``pdk_models`` hook, ``align/compiler/read_library.py``):
ALIGN's built-in ones (NMOS, PMOS, CAP, RES, IND) and frida's first-class devices, the MOM units
MomUnit draws (``flow/layout/primitives/mom.py``): each style a device of its own pins
(``flow/layout/devices/momcap/geometry.py``'s ``PINS``), called in a netlist like a transistor, with the
parameters its generator reads (``align_parameters``) and its capacitance. A PDK's
``user_template.sp`` (``flow/layout/make_pdk.py``) makes each one a primitive of MomUnit's, as
ALIGN's own CAP_2T is of its cap generator."""

# each style's device: its name (the netlist's model) and pins, in its view's order
MOM_DEVICES = {
    "FMOMCAP": ("INNER", "TOP", "SHIELD"),
    "FMOMDIFF": ("MAIN", "DIFF", "TOP", "SHIELD"),
    "FMOMSTRIP": ("A", "B", "SHIELD"),
}
# the parameters MomUnit reads (MomcapGeometry.align_parameters) and the design value, with defaults
MOM_PARAMETERS = {
    "C": 0,
    "C_DIFF": 0,  # a difference strip's difference plate's
    "STYLE": "RING",
    "LAYERS": 1,
    "LENGTH": 0,
    "DIFF_LENGTH": 0,
    "ABUT": 0,
    "LEFT": "EDGE",
    "RIGHT": "EDGE",
    "ABOVE": "EDGE",
    "BELOW": "EDGE",
    "FRAME": 0,
    "ARRAY": "CHANNELS",
    "PIN_BAND": 0,
}


def pdk_models():
    """ALIGN's built-in models and the MOM devices."""
    from align.schema.library import Library
    from align.schema.model import Model

    models = Library().default_models()
    for name, pins in MOM_DEVICES.items():
        models.append(Model(name=name, pins=list(pins), parameters=dict(MOM_PARAMETERS), prefix=""))
    return models


def templates() -> str:
    """The MOM devices' library templates: each device a primitive MomUnit draws."""
    out = []
    for name, pins in MOM_DEVICES.items():
        out += [
            f".subckt {name}_PRIM {' '.join(pins)}",
            "* @: Generator(name='MomUnit')",
            f"X0 {' '.join(pins)} {name}",
            f".ends {name}_PRIM",
            "",
        ]
    return "\n".join(out)
