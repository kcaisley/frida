"""ALIGN takes a ``CapGenerator`` from every PDK package; the row-cell flows have no capacitors."""


class CapGenerator:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("the row-cell ALIGN PDK (flow/layout/align/pdk) draws no capacitors")
