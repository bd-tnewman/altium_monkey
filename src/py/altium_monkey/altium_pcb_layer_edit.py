"""
Move existing PCB primitives to another layer.

A primitive's layer is stored more than once, and every copy has to change together or Altium
shows the primitive (or its group) on the old layer:

- every record keeps the legacy layer byte (Mechanical 17+ store 72 there);
- tracks, arcs and fills also keep a V7 saved-layer id (``v7_layer_id``), texts keep one in the
  barcode block (``barcode_layer_v7``), regions and 3D bodies keep a ``V7_LAYER`` token;
- shapes drawn with Altium's linked tools (Place Rectangle) keep a further copy of the group's layer
  in the footprint's ``SMARTUNION_ITEMn`` parameter, which Altium trusts over the member tracks.

Pads and vias are not handled: moving them between copper layers changes their pad stack, not just
a layer field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from .altium_pcb_layer_ref import (
    PcbLayerLike,
    PcbLayerRef,
    PcbLayerRegistry,
    _coerce_pcb_authoring_layer_storage,
)
from .altium_pcbdoc_builder_regions import region_v7_layer_text
from .altium_record_pcb__arc import AltiumPcbArc
from .altium_record_pcb__component_body import AltiumPcbComponentBody
from .altium_record_pcb__fill import AltiumPcbFill
from .altium_record_pcb__region import AltiumPcbRegion
from .altium_record_pcb__text import AltiumPcbText
from .altium_record_pcb__track import AltiumPcbTrack

SMART_UNION_PREFIX = "SMARTUNION_ITEM"
_SMART_UNION_LAYER = re.compile(r"(^|<Pipe>)LAYER<EQ>([^<]*)")
_SMART_UNION_FIELD = re.compile(r"(\w+)<EQ>([^<]*)")
# Footprint primitives are stored relative to the footprint origin; SmartUnion bounds are stored in
# absolute library-editor coordinates, whose origin sits at (50000 mil, 50000 mil).
_SMART_UNION_ORIGIN = 50000 * 10000
_RECTANGLE_UNION_TYPE = "9"
_TOLERANCE = 2  # internal units (0.0002 mil): the mil text in the union has 4 decimals


class PcbLayerEditError(ValueError):
    """The requested layer move can't be made without leaving the footprint inconsistent."""


def set_primitive_layer(
    primitive: object,
    layer: PcbLayerLike,
    *,
    registry: PcbLayerRegistry | None = None,
) -> PcbLayerRef:
    """
    Move one primitive to ``layer``, updating every per-record copy of its layer.

    Does not touch footprint-level SmartUnion parameters; use ``move_primitives_to_layer`` for
    primitives inside a footprint.
    """
    storage = _coerce_pcb_authoring_layer_storage(layer, registry=registry)
    if isinstance(primitive, (AltiumPcbTrack, AltiumPcbArc, AltiumPcbFill)):
        primitive.layer = storage.legacy_layer_id
        primitive.v7_layer_id = storage.v7_saved_layer_id
    elif isinstance(primitive, AltiumPcbText):
        primitive.layer = storage.legacy_layer_id
        primitive.barcode_layer_v7 = storage.v7_saved_layer_id
    elif isinstance(primitive, (AltiumPcbRegion, AltiumPcbComponentBody)):
        primitive.layer = storage.legacy_layer_id
        primitive.v7_layer = region_v7_layer_text(storage.ref)
    else:
        raise PcbLayerEditError(
            f"Moving a {type(primitive).__name__} to another layer is not supported"
        )
    return storage.ref


@dataclass(frozen=True)
class PcbSmartUnion:
    """One ``SMARTUNION_ITEMn`` footprint parameter (a linked shape such as a placed rectangle)."""

    key: str
    layer_token: str
    union_type: str
    bounds: tuple[int, int, int, int] | None  # footprint-relative internal units
    rotation: float
    members: tuple[AltiumPcbTrack, ...]  # empty when they can't be identified with certainty

    @property
    def is_identified(self) -> bool:
        return bool(self.members)


def footprint_smart_unions(footprint: object) -> list[PcbSmartUnion]:
    """SmartUnion parameters of a footprint, with the member tracks of placed rectangles."""
    unions = []
    for key, value in getattr(footprint, "parameters", {}).items():
        if not key.upper().startswith(SMART_UNION_PREFIX):
            continue
        fields = dict(_SMART_UNION_FIELD.findall(value))
        layer = _SMART_UNION_LAYER.search(value)
        bounds = _union_bounds(fields)
        try:
            rotation = float(fields.get("ROTATION", "0") or 0)
        except ValueError:
            rotation = float("nan")
        union = PcbSmartUnion(
            key=key,
            layer_token=layer.group(2) if layer else "",
            union_type=fields.get("UNIONTYPE", ""),
            bounds=bounds,
            rotation=rotation,
            members=(),
        )
        unions.append(replace(union, members=_rectangle_members(footprint, union)))
    return unions


def move_primitives_to_layer(
    footprint: object,
    primitives: Iterable[object],
    layer: PcbLayerLike,
    *,
    registry: PcbLayerRegistry | None = None,
) -> int:
    """
    Move primitives of ``footprint`` to ``layer``, keeping its SmartUnion parameters in step.

    A placed rectangle moves as a whole, as it does in Altium: moving only some of its sides is
    refused, and so is moving a track that may belong to a linked shape this module can't identify.
    Nothing is changed when the move is refused. Returns the number of primitives moved.
    """
    moving = list(dict.fromkeys(primitives))
    target = _coerce_pcb_authoring_layer_storage(layer, registry=registry).ref
    for p in moving:
        if not isinstance(
            p,
            (AltiumPcbTrack, AltiumPcbArc, AltiumPcbFill, AltiumPcbText, AltiumPcbRegion,
             AltiumPcbComponentBody),
        ):
            raise PcbLayerEditError(
                f"Moving a {type(p).__name__} to another layer is not supported"
            )

    moving_ids = {id(p) for p in moving}
    union_updates: dict[str, str] = {}
    for union in footprint_smart_unions(footprint):
        if union.is_identified:
            moved = [m for m in union.members if id(m) in moving_ids]
            if not moved:
                continue
            if len(moved) != len(union.members):
                raise PcbLayerEditError(
                    f"{len(moved)} of the {len(union.members)} sides of a linked rectangle on "
                    f"{union.layer_token} would move; move all of its sides together"
                )
            union_updates[union.key] = target.token
            continue
        suspects = [
            p for p in moving
            if isinstance(p, AltiumPcbTrack)
            and _layer_token(p, registry) == union.layer_token
            and (union.bounds is None or _inside(_track_extent(p), union.bounds))
        ]
        if suspects:
            raise PcbLayerEditError(
                f"Track(s) on {union.layer_token} may belong to a linked shape "
                f"({union.key}, type {union.union_type or '?'}) that can't be moved safely"
            )

    for p in moving:
        set_primitive_layer(p, target, registry=registry)
    for key, token in union_updates.items():
        value = footprint.parameters[key]
        footprint.parameters[key] = _SMART_UNION_LAYER.sub(
            lambda m: f"{m.group(1)}LAYER<EQ>{token}", value, count=1
        )
    return len(moving)


def _layer_token(primitive: object, registry: PcbLayerRegistry | None) -> str:
    return primitive.layer_ref(registry=registry).token


SMART_UNION_COUNT_KEY = "SMARTUNIONSSTORAGE"


def remove_smart_unions(footprint: object, unions: Iterable[PcbSmartUnion]) -> int:
    """
    Delete placed rectangles from a footprint opened with ``edit_footprint``: their side tracks and
    their ``SMARTUNION_ITEMn`` entries. The remaining entries are renumbered from 0 (rewritten in the
    form Altium uses when it re-saves them) and ``SMARTUNIONSSTORAGE`` holds their count; with none
    left both keys go. Checked against Altium deleting the only rectangle of 8-UFDFN-EP (2x3) and the
    first of two in 8-X2SON. Returns the number of tracks removed.
    """
    doomed = list(unions)
    for union in doomed:
        if not union.is_identified:
            raise PcbLayerEditError(
                f"The linked shape {union.key} on {union.layer_token} can't be identified; "
                "it can't be deleted safely"
            )
    removed = 0
    for union in doomed:
        for track in union.members:
            footprint.remove_primitive(track)
            removed += 1
    params = footprint.parameters
    keep = [params[k] for k in sorted(
        (k for k in params if k.upper().startswith(SMART_UNION_PREFIX)),
        key=lambda k: int(k[len(SMART_UNION_PREFIX):] or 0),
    ) if k not in {u.key for u in doomed}]
    rebuilt = {}
    for key, value in params.items():
        if key.upper().startswith(SMART_UNION_PREFIX) or key.upper() == SMART_UNION_COUNT_KEY:
            continue
        rebuilt[key] = value
    if keep:
        rebuilt[SMART_UNION_COUNT_KEY] = str(len(keep))
        for i, value in enumerate(keep):
            rebuilt[f"{SMART_UNION_PREFIX}{i}"] = _current_union_text(value)
    params.clear()
    params.update(rebuilt)
    return removed


def _current_union_text(value: str) -> str:
    """
    A SmartUnion entry in the form current Altium writes when it re-saves a footprint's unions
    (checked against Altium renumbering 8-X2SON): leading ``<Pipe>``, the rotation's sign column kept as
    a space, and X1/Y1 repeated after FUNIONINDEX. Entries already in that form are left as they are.
    """
    if value.startswith("<Pipe>"):
        return value
    fields = dict(_SMART_UNION_FIELD.findall(value))
    text = "<Pipe>" + re.sub(r"(ROTATION<EQ>)(?=[0-9])", r"\1 ", value, count=1)
    if "X1" in fields and "Y1" in fields:
        text = re.sub(
            r"(<Pipe>FUNIONINDEX<EQ>[^<]*)",
            lambda m: f"{m.group(1)}<Pipe>X1<EQ>{fields['X1']}<Pipe>Y1<EQ>{fields['Y1']}",
            text,
            count=1,
        )
    return text


def _union_bounds(fields: dict[str, str]) -> tuple[int, int, int, int] | None:
    try:
        x1, y1, x2, y2 = (
            int(round(float(fields[k].removesuffix("mil")) * 10000)) - _SMART_UNION_ORIGIN
            for k in ("X1", "Y1", "X2", "Y2")
        )
    except (KeyError, ValueError):
        return None
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _track_extent(t: AltiumPcbTrack) -> tuple[int, int, int, int]:
    hw = int(t.width) / 2
    return (
        min(t.start_x, t.end_x) - hw,
        min(t.start_y, t.end_y) - hw,
        max(t.start_x, t.end_x) + hw,
        max(t.start_y, t.end_y) + hw,
    )


def _inside(extent, bounds) -> bool:
    return (
        extent[0] >= bounds[0] - _TOLERANCE
        and extent[1] >= bounds[1] - _TOLERANCE
        and extent[2] <= bounds[2] + _TOLERANCE
        and extent[3] <= bounds[3] + _TOLERANCE
    )


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= _TOLERANCE


def _rectangle_members(footprint: object, union: PcbSmartUnion) -> tuple[AltiumPcbTrack, ...]:
    """
    The 4 side tracks of an unrotated placed rectangle: each one runs along an edge of the union's
    bounds. Anything less certain returns () so callers treat the union as unidentified.
    """
    if union.union_type != _RECTANGLE_UNION_TYPE or union.bounds is None or union.rotation != 0:
        return ()
    x1, y1, x2, y2 = union.bounds
    sides = []
    for t in getattr(footprint, "tracks", ()):
        if _layer_token(t, None) != union.layer_token:
            continue
        hw = int(t.width) / 2
        lo_x, hi_x = sorted((t.start_x, t.end_x))
        lo_y, hi_y = sorted((t.start_y, t.end_y))
        horizontal = _near(t.start_y, t.end_y) and _near(lo_x, x1 + hw) and _near(hi_x, x2 - hw)
        vertical = _near(t.start_x, t.end_x) and _near(lo_y, y1 + hw) and _near(hi_y, y2 - hw)
        if horizontal and (_near(t.start_y, y1 + hw) or _near(t.start_y, y2 - hw)):
            sides.append(t)
        elif vertical and (_near(t.start_x, x1 + hw) or _near(t.start_x, x2 - hw)):
            sides.append(t)
    return tuple(sides) if len(sides) == 4 else ()
