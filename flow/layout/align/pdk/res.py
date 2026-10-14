"""ALIGN takes a ``ResGenerator`` from every PDK package; the row-cell flows have no resistors."""


class ResGenerator:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("the row-cell ALIGN PDK (flow/layout/align/pdk) draws no resistors")
