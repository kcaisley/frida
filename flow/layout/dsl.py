"""Typed layout DSL: generic layers, params, and generator decorators."""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field
from enum import Enum, IntEnum, auto
import inspect
from typing import Any, Callable, cast, get_type_hints


class Layer(Enum):
    """Generic process-agnostic layers used by generators."""

    OD = auto()
    PO = auto()
    CO = auto()
    M1 = auto()
    VIA1 = auto()
    M2 = auto()
    VIA2 = auto()
    M3 = auto()
    VIA3 = auto()
    M4 = auto()
    VIA4 = auto()
    M5 = auto()
    VIA5 = auto()
    M6 = auto()
    VIA6 = auto()
    M7 = auto()
    VIA7 = auto()
    M8 = auto()
    VIA8 = auto()
    M9 = auto()
    VIA9 = auto()
    M10 = auto()
    NP = auto()
    PP = auto()
    NWELL = auto()
    TEXT = auto()
    PR_BOUNDARY = auto()
    VTH_LVT = auto()
    VTH_HVT = auto()

    @property
    def draw(self) -> LayerRef:
        return LayerRef(self, Purpose.DRAW)

    @property
    def pin(self) -> LayerRef:
        return LayerRef(self, Purpose.PIN)


class Purpose(IntEnum):
    DRAW = 0
    PIN = 1


@dataclass(frozen=True)
class LayerRef:
    layer: Layer
    purpose: Purpose


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


METAL_DRAW_TO_GENERIC: dict[MetalDraw, Layer] = {
    MetalDraw.M1: Layer.M1,
    MetalDraw.M2: Layer.M2,
    MetalDraw.M3: Layer.M3,
    MetalDraw.M4: Layer.M4,
    MetalDraw.M5: Layer.M5,
    MetalDraw.M6: Layer.M6,
    MetalDraw.M7: Layer.M7,
    MetalDraw.M8: Layer.M8,
    MetalDraw.M9: Layer.M9,
    MetalDraw.M10: Layer.M10,
}


VTH_TO_GENERIC: dict[MosVth, Layer | None] = {
    MosVth.LOW: Layer.VTH_LVT,
    MosVth.REGULAR: None,
    MosVth.HIGH: Layer.VTH_HVT,
}


def generic_name(ref: LayerRef) -> str:
    if ref.purpose == Purpose.DRAW:
        return f"{ref.layer.name}.draw"
    if ref.purpose == Purpose.PIN:
        return f"{ref.layer.name}.pin"
    raise ValueError("Unsupported layer purpose.")


def param_to_generic(
    *,
    metal: MetalDraw | None = None,
    vth: MosVth | None = None,
) -> Layer | None:
    """Map typed parameter selectors to generic layers."""

    if (metal is None) == (vth is None):
        raise ValueError("Pass exactly one selector: metal or vth.")
    if metal is not None:
        return METAL_DRAW_TO_GENERIC[metal]
    return VTH_TO_GENERIC[cast(MosVth, vth)]


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


class _LayoutNamespace:
    """Single namespace API: layers + params + decorators."""

    Param = Param
    Layer = Layer
    LayerRef = LayerRef
    Purpose = Purpose
    MosType = MosType
    MosVth = MosVth
    SourceTie = SourceTie
    MetalDraw = MetalDraw
    METAL_DRAW_TO_GENERIC = METAL_DRAW_TO_GENERIC
    VTH_TO_GENERIC = VTH_TO_GENERIC

    paramclass = staticmethod(paramclass)
    generator = staticmethod(generator)
    generic_name = staticmethod(generic_name)
    param_to_generic = staticmethod(param_to_generic)

    def __init__(self) -> None:
        for member in Layer:
            setattr(self, member.name, member)


L = _LayoutNamespace()

__all__ = [
    "L",
    "Layer",
    "LayerRef",
    "Purpose",
    "MosType",
    "MosVth",
    "SourceTie",
    "MetalDraw",
    "METAL_DRAW_TO_GENERIC",
    "VTH_TO_GENERIC",
    "Param",
    "paramclass",
    "generator",
    "generic_name",
    "param_to_generic",
]
