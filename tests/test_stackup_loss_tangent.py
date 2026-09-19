import pytest

from altium_monkey import AltiumLayerStackDocument
from altium_monkey import AltiumRigidCopperLayerSpec
from altium_monkey import AltiumStackupDocument
from altium_monkey.altium_layer_stack_document import AltiumStackLayer


def _loss_tangent_layer(*fields: str) -> AltiumStackLayer:
    rows = [
        "LAYER_V8_0NAME=Dielectric 1",
        "LAYER_V8_0TYPEID={92B02D5E-8D69-48A8-880E-AC4B77DB099D}",
        *fields,
    ]
    model = AltiumStackupDocument.from_text(
        "|" + "|".join(rows)
    ).to_layer_stack_document()
    return model.physical_stacks[0].layers[0]


def _semantic_stack(layer: AltiumStackLayer) -> AltiumLayerStackDocument:
    return AltiumLayerStackDocument.from_rigid_layer_rows(
        name="Loss tangent compatibility",
        rows=(
            AltiumRigidCopperLayerSpec(name="Top Layer"),
            layer,
            AltiumRigidCopperLayerSpec(name="Bottom Layer"),
        ),
    )


def test_stackup_loss_tangent_accepts_altium_and_legacy_fields() -> None:
    assert (
        _loss_tangent_layer("LAYER_V8_0$LSM$LossTangent=0.002").dielectric_loss_tangent
        == 0.002
    )
    assert (
        _loss_tangent_layer("LAYER_V8_0DIELLOSSTANGENT=0.003").dielectric_loss_tangent
        == 0.003
    )
    assert (
        _loss_tangent_layer(
            "LAYER_V8_0DIELLOSSTANGENT=0.003",
            "LAYER_V8_0$LSM$LossTangent=0.002",
        ).dielectric_loss_tangent
        == 0.002
    )


@pytest.mark.parametrize("token", ["", "invalid", "NaN", "Infinity"])
def test_present_invalid_lsm_loss_tangent_blocks_legacy_fallback(token: str) -> None:
    layer = _loss_tangent_layer(
        f"LAYER_V8_0$LSM$LossTangent={token}",
        "LAYER_V8_0DIELLOSSTANGENT=0.003",
    )

    assert layer.dielectric_loss_tangent is None


def test_semantic_stackup_export_synchronizes_both_loss_tangent_fields() -> None:
    raw = (
        "|LAYER_V8_0NAME=Dielectric 1"
        "|LAYER_V8_0DIELLOSSTANGENT=0.003"
        "|LAYER_V8_0$LSM$LossTangent=0.002\n"
    )
    stackup = AltiumStackupDocument.from_text(raw)
    assert stackup.to_text() == raw

    source_layer = stackup.to_layer_stack_document().physical_stacks[0].layers[0]
    exported = AltiumStackupDocument.from_text(
        _semantic_stack(source_layer).to_stackup_text()
    ).to_record_mapping()

    assert exported["LAYER_V8_1DIELLOSSTANGENT"] == "0.002"
    assert exported["LAYER_V8_1$LSM$LossTangent"] == "0.002"


def test_semantic_stackup_export_does_not_revive_rejected_fallback() -> None:
    layer = _loss_tangent_layer(
        "LAYER_V8_0$LSM$LossTangent=invalid",
        "LAYER_V8_0DIELLOSSTANGENT=0.003",
    )

    exported = AltiumStackupDocument.from_text(_semantic_stack(layer).to_stackup_text())
    reopened = exported.to_layer_stack_document().physical_stacks[0].layers[1]

    assert reopened.dielectric_loss_tangent is None
    assert not any("LOSSTANGENT" in key.upper() for key, _value in exported.records)
