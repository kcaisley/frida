"""Typed layout DSL: generic layers, params, and generator decorators."""

from __future__ import annotations

import inspect
from dataclasses import MISSING, dataclass, field
from enum import IntEnum
from typing import Any, Callable, get_type_hints

import klayout.db as kdb

# ---------------------------------------------------------------------------
# Parameter enums — used by generators via L.MosType, L.MosVth, etc.
# ---------------------------------------------------------------------------


class MosType(IntEnum):
    NMOS = 0
    PMOS = 1


class MosVth(IntEnum):
    LOW = 0
    REGULAR = 1
    HIGH = 2


class SourceTie(IntEnum):
    OFF = 0
    ON = 1


class MetalDraw(IntEnum):
    M1 = 1
    M2 = 2
    M3 = 3
    M4 = 4
    M5 = 5
    M6 = 6
    M7 = 7
    M8 = 8
    M9 = 9
    M10 = 10


# ---------------------------------------------------------------------------
# GenericLayers — process-agnostic kdb.LayerInfo namespace
# ---------------------------------------------------------------------------


class GenericLayers:
    """Namespace of kdb.LayerInfo objects for all generic process layers.

    Each attribute (e.g. .M1, .PIN1, .OD) is a kdb.LayerInfo with a
    canonical name and default layer/datatype numbers.  These can be
    passed directly to cell.shapes(G.M1).insert(...).
    """

    # Draw layers — (layer_number, datatype, name)
    OD = kdb.LayerInfo(1, 0, "OD")
    PO = kdb.LayerInfo(2, 0, "PO")
    CO = kdb.LayerInfo(3, 0, "CO")
    NP = kdb.LayerInfo(4, 0, "NP")
    PP = kdb.LayerInfo(5, 0, "PP")
    NW = kdb.LayerInfo(6, 0, "NW")
    DNW = kdb.LayerInfo(6, 1, "DNW")

    # Threshold voltage layers — datatype 0 = N, datatype 1 = P
    LVTN = kdb.LayerInfo(7, 0, "LVTN")
    LVTP = kdb.LayerInfo(7, 1, "LVTP")
    HVTN = kdb.LayerInfo(8, 0, "HVTN")
    HVTP = kdb.LayerInfo(8, 1, "HVTP")

    # Metal stack starts at layer 10
    M1 = kdb.LayerInfo(10, 0, "M1")
    VIA1 = kdb.LayerInfo(11, 0, "VIA1")
    M2 = kdb.LayerInfo(12, 0, "M2")
    VIA2 = kdb.LayerInfo(13, 0, "VIA2")
    M3 = kdb.LayerInfo(14, 0, "M3")
    VIA3 = kdb.LayerInfo(15, 0, "VIA3")
    M4 = kdb.LayerInfo(16, 0, "M4")
    VIA4 = kdb.LayerInfo(17, 0, "VIA4")
    M5 = kdb.LayerInfo(18, 0, "M5")
    VIA5 = kdb.LayerInfo(19, 0, "VIA5")
    M6 = kdb.LayerInfo(20, 0, "M6")
    VIA6 = kdb.LayerInfo(21, 0, "VIA6")
    M7 = kdb.LayerInfo(22, 0, "M7")
    VIA7 = kdb.LayerInfo(23, 0, "VIA7")
    M8 = kdb.LayerInfo(24, 0, "M8")
    VIA8 = kdb.LayerInfo(25, 0, "VIA8")
    M9 = kdb.LayerInfo(26, 0, "M9")
    VIA9 = kdb.LayerInfo(27, 0, "VIA9")
    M10 = kdb.LayerInfo(28, 0, "M10")

    # Pin layers — same layer number as corresponding metal, datatype 1
    PIN1 = kdb.LayerInfo(10, 1, "PIN1")
    PIN2 = kdb.LayerInfo(12, 1, "PIN2")
    PIN3 = kdb.LayerInfo(14, 1, "PIN3")
    PIN4 = kdb.LayerInfo(16, 1, "PIN4")
    PIN5 = kdb.LayerInfo(18, 1, "PIN5")
    PIN6 = kdb.LayerInfo(20, 1, "PIN6")
    PIN7 = kdb.LayerInfo(22, 1, "PIN7")
    PIN8 = kdb.LayerInfo(24, 1, "PIN8")
    PIN9 = kdb.LayerInfo(26, 1, "PIN9")

    # Special layers
    TEXT = kdb.LayerInfo(60, 0, "TEXT")
    PR_BOUNDARY = kdb.LayerInfo(61, 0, "PR_BOUNDARY")


def load_generic_layers(layout: kdb.Layout) -> GenericLayers:
    """Register all generic layers in *layout* and return the namespace.

    Calls ``layout.layer(info)`` for every ``kdb.LayerInfo`` on
    ``GenericLayers``.  This ensures the layers exist in the layout's
    layer table.  Returns a ``GenericLayers`` instance so that
    ``G.M1``, ``G.PIN2`` etc. resolve to ``kdb.LayerInfo`` objects
    usable in ``cell.shapes(G.M1).insert(...)``.
    """
    layers = GenericLayers()
    for name in dir(layers):
        if name.startswith("_"):
            continue
        val = getattr(layers, name)
        if isinstance(val, kdb.LayerInfo):
            layout.layer(val)  # register in layout
    return layers


# ---------------------------------------------------------------------------
# Param / paramclass / generator — layout parameter infrastructure
# ---------------------------------------------------------------------------


class Param:
    """Field-marker used by `@paramclass`."""

    def __init__(
        self,
        *,
        dtype: Any = Any,
        desc: str = "",
        default: Any = MISSING,
        default_factory: Callable[[], Any] | None = None,
        validator: Callable[[Any], bool] | None = None,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ValueError("Param cannot define both default and default_factory.")
        self.dtype = dtype
        self.desc = desc
        self.default = default
        self.default_factory = default_factory
        self.validator = validator


def paramclass(
    cls: type[Any],
    *,
    frozen: bool = True,
    slots: bool = True,
) -> type[Any]:
    """Convert `Param(...)` fields into a dataclass."""

    from typing import cast

    # 1) Start from any existing annotations declared on the class.
    annotations = dict(getattr(cls, "__annotations__", {}))
    # 2) Walk every attribute defined directly on the class.
    for name, value in list(vars(cls).items()):
        # 3) Ignore attributes that are not Param markers.
        if not isinstance(value, Param):
            continue
        # 4) Treat the Param marker as the spec for this field.
        spec = value
        # 5) Read the currently-declared annotation (if any).
        declared = annotations.get(name, Any)
        # 6) If the field was not annotated, infer its type from spec.dtype.
        if name not in annotations:
            # 7) Reject missing type information when neither annotation nor dtype exists.
            if spec.dtype is Any:
                raise TypeError(
                    f"Parameter '{name}' requires either dtype or annotation."
                )
            # 8) Persist inferred annotation so dataclass sees the field type.
            annotations[name] = spec.dtype
            declared = spec.dtype

        # 9) If both dtype and annotation are explicit, require exact agreement.
        if spec.dtype is not Any and declared is not Any:
            if spec.dtype != declared:
                raise TypeError(
                    f"Parameter '{name}' dtype/ annotation mismatch: "
                    f"dtype={spec.dtype}, annotation={declared}."
                )

        # 10) Compute effective expected type for default-value checks.
        expected = spec.dtype if spec.dtype is not Any else declared
        # 11) Validate literal default values when present.
        if spec.default is not MISSING:
            # 12) Assume valid until a concrete check disproves it.
            matches_type = True
            # 13) Skip runtime type checking for Any/object expectations.
            if expected not in (Any, object):
                # 14) For concrete classes, require isinstance(default, expected).
                if isinstance(expected, type):
                    expected_type = cast(type[object], expected)
                    matches_type = isinstance(spec.default, expected_type)
            # 15) Raise if literal default type is incompatible.
            if not matches_type:
                raise TypeError(
                    f"Invalid default type for '{name}': "
                    f"expected {expected}, got {type(spec.default).__name__}."
                )
            # 16) Run optional value validator on literal defaults.
            if spec.validator is not None and spec.validator(spec.default) is False:
                raise ValueError(
                    f"Validator rejected default value for parameter '{name}'."
                )

        # 17) Build metadata payload carried by the dataclass field.
        metadata = {"layout_param_spec": spec, "desc": spec.desc}
        # 18) Convert Param into dataclass field, preserving default semantics.
        if spec.default is MISSING and spec.default_factory is None:
            target_field = field(metadata=metadata)
        elif spec.default_factory is not None:
            target_field = field(
                default_factory=spec.default_factory,
                metadata=metadata,
            )
        else:
            target_field = field(default=spec.default, metadata=metadata)
        # 19) Replace the class attribute with the generated dataclass field object.
        setattr(cls, name, target_field)

    # 20) Write back finalized annotations for dataclass processing.
    cls.__annotations__ = annotations
    # 21) Apply dataclass transform with caller-selected frozen/slots options.
    out = dataclass(frozen=frozen, slots=slots)(cls)
    # 22) Mark output type so generator() can verify parameter-class annotations.
    setattr(out, "__layout_paramclass__", True)
    # 23) Return transformed class.
    return out


def generator(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for layout generators with first-argument type checks."""

    # 1) Capture function signature once for validation.
    signature = inspect.signature(fn)
    # 2) Materialize ordered parameter list.
    parameters = tuple(signature.parameters.values())
    # 3) Require at least (params, tech).
    if len(parameters) < 2:
        raise TypeError("Layout generator must accept (params, tech).")

    # 4) Inspect first parameter, which must be the param class.
    first = parameters[0]
    # 5) Resolve postponed annotations (from __future__) into real Python objects.
    resolved_hints = get_type_hints(fn, globalns=fn.__globals__, localns=None)
    first_annotation = resolved_hints.get(first.name, first.annotation)
    # 6) Require an explicit type annotation on first parameter.
    if first_annotation is inspect._empty:
        raise TypeError(
            "First generator argument must be a @paramclass type annotation."
        )
    # 7) Require that annotation to be produced by @paramclass.
    if not hasattr(first_annotation, "__layout_paramclass__"):
        raise TypeError(
            f"First generator argument must be a @paramclass type, got {first_annotation}."
        )

    # 8) Tag function for optional downstream introspection.
    setattr(fn, "__layout_generator__", True)
    # 9) Store validated signature for optional downstream tooling.
    setattr(fn, "__layout_generator_signature__", signature)
    # 10) Return original function unchanged.
    return fn


# ---------------------------------------------------------------------------
# L — convenience namespace used by generators as L.Param, L.MosType, etc.
# ---------------------------------------------------------------------------


class _LayoutNamespace:
    """Single namespace exposing params, decorators, and enums."""

    Param = Param
    MosType = MosType
    MosVth = MosVth
    SourceTie = SourceTie
    MetalDraw = MetalDraw

    paramclass = staticmethod(paramclass)
    generator = staticmethod(generator)


L = _LayoutNamespace()

__all__ = [
    "L",
    "MosType",
    "MosVth",
    "SourceTie",
    "MetalDraw",
    "Param",
    "paramclass",
    "generator",
    # New API
    "GenericLayers",
    "load_generic_layers",
]
