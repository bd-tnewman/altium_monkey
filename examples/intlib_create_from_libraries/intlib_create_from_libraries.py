from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from altium_monkey import (
    AltiumIntLib,
    AltiumPcbLib,
    AltiumSchLib,
    IntLibBuildResult,
)
from altium_monkey.altium_schlib import AltiumSymbol


SAMPLE_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = SAMPLE_DIR.parent
ASSETS_DIR = EXAMPLES_DIR / "assets"
SCHLIB_ASSETS_DIR = ASSETS_DIR / "schlib"
IC_PCBLIB_ASSET = ASSETS_DIR / "pcblib" / "RT_SUPER_C1.PcbLib"
RESISTOR_PCBLIB_ASSET = ASSETS_DIR / "pcblib" / "R0603_0.55MM_MD.PcbLib"
OUTPUT_DIR = SAMPLE_DIR / "output"
MULTI_SOURCE_DIR = OUTPUT_DIR / "prepared" / "multi_source"
AGGREGATE_DIR = OUTPUT_DIR / "prepared" / "aggregate"
MULTI_SOURCE_INTLIB = OUTPUT_DIR / "ic-subset-multi-source.IntLib"
AGGREGATE_INTLIB = OUTPUT_DIR / "ic-subset-aggregate.IntLib"
MANIFEST_PATH = OUTPUT_DIR / "intlib_create_manifest.json"


@dataclass(frozen=True)
class ComponentSpec:
    source_name: str
    output_name: str
    symbol_name: str
    value: str
    manufacturer: str
    part_number: str
    footprints: tuple[str, ...]


COMPONENTS = (
    ComponentSpec(
        "MIMXRT685SFVKB.Schlib",
        "MIMXRT685SFVKB.SchLib",
        "MIMXRT685SFVKB",
        "i.MX RT685",
        "NXP",
        "MIMXRT685SFVKB",
        ("VFBGA176",),
    ),
    ComponentSpec(
        "24LC32AT.SchLib",
        "24LC32AT.SchLib",
        "24LC32AT",
        "32-Kbit I2C EEPROM",
        "Microchip",
        "24LC32AT",
        ("SOT23-5",),
    ),
    ComponentSpec(
        "MX25R6435FZNIL0.Schlib",
        "MX25R6435FZNIL0.SchLib",
        "MX25R6435FZNIL0",
        "64-Mbit SPI flash",
        "Macronix",
        "MX25R6435FZNIL0",
        ("W25Q_XSON_8",),
    ),
    ComponentSpec(
        "SM712-02HTG.Schlib",
        "SM712-02HTG.SchLib",
        "SM712-02HTG",
        "12 V protection array",
        "Littelfuse",
        "SM712-02HTG",
        ("SOT143B",),
    ),
    ComponentSpec(
        "SM712-02HTG.Schlib",
        "SM712.TCT.SchLib",
        "SM712.TCT",
        "12 V protection array, alternate ordering code",
        "Littelfuse",
        "SM712.TCT",
        ("SOT143B", "D_SOD-323_P"),
    ),
    ComponentSpec(
        "R_2P.Schlib",
        "RC0603FR-0710KL.SchLib",
        "RC0603FR-0710KL",
        "10 kohm 1%",
        "Yageo",
        "RC0603FR-0710KL",
        ("R0603_0.55MM_MD",),
    ),
    ComponentSpec(
        "R_2P.Schlib",
        "RC0603FR-074K7L.SchLib",
        "RC0603FR-074K7L",
        "4.7 kohm 1%",
        "Yageo",
        "RC0603FR-074K7L",
        ("R0603_0.55MM_MD",),
    ),
)

FOOTPRINT_NAMES = (
    "VFBGA176",
    "SOT23-5",
    "W25Q_XSON_8",
    "SOT143B",
    "D_SOD-323_P",
    "PCA9420",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sample_relative(path: Path) -> str:
    return str(path.relative_to(SAMPLE_DIR)).replace("\\", "/")


def _reset_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    (MULTI_SOURCE_DIR / "schlib").mkdir(parents=True)
    (MULTI_SOURCE_DIR / "pcblib").mkdir(parents=True)
    AGGREGATE_DIR.mkdir(parents=True)


def _set_or_add_parameter(symbol: AltiumSymbol, name: str, value: str) -> None:
    for parameter in symbol.parameters:
        if parameter.name.casefold() == name.casefold():
            parameter.text = value
            parameter.is_hidden = True
            return
    symbol.add_parameter(name, value, is_hidden=True)


def _prepare_schlibs() -> tuple[Path, ...]:
    output_paths: list[Path] = []
    for spec in COMPONENTS:
        library = AltiumSchLib(SCHLIB_ASSETS_DIR / spec.source_name)
        symbol = library.symbols[0]
        if symbol.name != spec.symbol_name:
            symbol = library.rename_symbol(
                symbol,
                spec.symbol_name,
                original_name=spec.symbol_name,
            )
        _set_or_add_parameter(symbol, "Value", spec.value)
        _set_or_add_parameter(symbol, "Manufacturer", spec.manufacturer)
        _set_or_add_parameter(symbol, "Manufacturer Part Number", spec.part_number)
        _set_or_add_parameter(symbol, "Category", "IC and protection subset")
        for index, footprint_name in enumerate(spec.footprints):
            symbol.add_footprint(
                footprint_name,
                description=("Default package" if index == 0 else "Alternate package"),
                is_current=index == 0,
                library_name="ICSubset",
            )
        output_path = MULTI_SOURCE_DIR / "schlib" / spec.output_name
        library.save(output_path)
        output_paths.append(output_path)
    return tuple(output_paths)


def _prepare_pcblibs() -> tuple[Path, ...]:
    output_paths: list[Path] = []
    with tempfile.TemporaryDirectory(
        prefix="intlib-example-split-", dir=OUTPUT_DIR
    ) as temp_dir:
        split = AltiumPcbLib.from_file(IC_PCBLIB_ASSET).split(Path(temp_dir))
        for footprint_name in FOOTPRINT_NAMES:
            output_path = MULTI_SOURCE_DIR / "pcblib" / f"{footprint_name}.PcbLib"
            shutil.copy2(split[footprint_name], output_path)
            output_paths.append(output_path)
    resistor_output = MULTI_SOURCE_DIR / "pcblib" / RESISTOR_PCBLIB_ASSET.name
    shutil.copy2(RESISTOR_PCBLIB_ASSET, resistor_output)
    output_paths.append(resistor_output)
    return tuple(output_paths)


def _prepare_aggregate(
    schlib_paths: tuple[Path, ...],
    pcblib_paths: tuple[Path, ...],
) -> tuple[Path, Path]:
    schlib_path = AGGREGATE_DIR / "ICSubset.SchLib"
    pcblib_path = AGGREGATE_DIR / "ICSubset.PcbLib"
    AltiumSchLib.merge(
        list(schlib_paths),
        schlib_path,
        handle_conflicts="error",
        verbose=False,
    )
    AltiumPcbLib.combine(list(pcblib_paths)).save(pcblib_path)
    return schlib_path, pcblib_path


def _component_graph(intlib_path: Path) -> dict[str, list[str]]:
    with AltiumIntLib(intlib_path) as intlib:
        return {
            component.name: [model.name for model in component.models]
            for component in intlib.components
        }


def _build_manifest_entry(
    intlib_path: Path,
    result: IntLibBuildResult,
) -> dict[str, object]:
    with AltiumIntLib(intlib_path) as intlib:
        extracted_hashes = {
            source.stream_path: _sha256(intlib.read_stream(source.stream_path))
            for source in result.sources
        }
        embedded_model_count = sum(
            len(
                AltiumPcbLib.from_bytes(
                    intlib.read_stream(source.stream_path),
                    filename=source.logical_name,
                ).embedded_model_summaries()
            )
            for source in result.sources
            if source.kind == "PCBLib"
        )
        stream_paths = list(intlib.stream_paths)
    sources = [
        {
            "kind": source.kind,
            "logical_name": source.logical_name,
            "stream_path": source.stream_path,
            "sha256": source.sha256,
            "entity_count": source.entity_count,
        }
        for source in result.sources
    ]
    return {
        "intlib": _sample_relative(intlib_path),
        "output_sha256": result.output_sha256,
        "source_count": result.source_count,
        "component_count": result.component_count,
        "footprint_count": result.footprint_count,
        "footprint_link_count": result.model_count,
        "embedded_model_count": embedded_model_count,
        "parameter_record_count": result.parameter_record_count,
        "sources": sources,
        "extracted_source_sha256": extracted_hashes,
        "source_hashes_match": all(
            source.sha256 == extracted_hashes[source.stream_path]
            for source in result.sources
        ),
        "stream_paths": stream_paths,
        "warnings": [
            {
                "code": warning.code.value,
                "subject": warning.subject,
                "message": warning.message,
            }
            for warning in result.warnings
        ],
    }


def _repeat_is_identical(
    output_path: Path,
    *,
    schlib_paths: tuple[Path, ...],
    pcblib_paths: tuple[Path, ...],
) -> bool:
    repeat_path = output_path.with_name(f"{output_path.stem}-repeat.IntLib")
    AltiumIntLib.create_from_libraries(
        repeat_path,
        schlib_paths=schlib_paths,
        pcblib_paths=pcblib_paths,
    )
    try:
        return repeat_path.read_bytes() == output_path.read_bytes()
    finally:
        repeat_path.unlink(missing_ok=True)


def create_intlibs() -> dict[str, object]:
    _reset_output()
    schlib_paths = _prepare_schlibs()
    pcblib_paths = _prepare_pcblibs()
    aggregate_schlib, aggregate_pcblib = _prepare_aggregate(
        schlib_paths,
        pcblib_paths,
    )

    multi_source_result = AltiumIntLib.create_from_libraries(
        MULTI_SOURCE_INTLIB,
        schlib_paths=schlib_paths,
        pcblib_paths=pcblib_paths,
    )
    aggregate_result = AltiumIntLib.create_from_libraries(
        AGGREGATE_INTLIB,
        schlib_paths=(aggregate_schlib,),
        pcblib_paths=(aggregate_pcblib,),
    )
    multi_source_graph = _component_graph(MULTI_SOURCE_INTLIB)
    aggregate_graph = _component_graph(AGGREGATE_INTLIB)

    manifest: dict[str, object] = {
        "prepared": {
            "multi_source_schlibs": [_sample_relative(path) for path in schlib_paths],
            "multi_source_pcblibs": [_sample_relative(path) for path in pcblib_paths],
            "aggregate_schlib": _sample_relative(aggregate_schlib),
            "aggregate_pcblib": _sample_relative(aggregate_pcblib),
        },
        "builds": {
            "multi_source": _build_manifest_entry(
                MULTI_SOURCE_INTLIB,
                multi_source_result,
            ),
            "aggregate": _build_manifest_entry(
                AGGREGATE_INTLIB,
                aggregate_result,
            ),
        },
        "component_graph": multi_source_graph,
        "component_graphs_match": multi_source_graph == aggregate_graph,
        "deterministic": {
            "multi_source": _repeat_is_identical(
                MULTI_SOURCE_INTLIB,
                schlib_paths=schlib_paths,
                pcblib_paths=pcblib_paths,
            ),
            "aggregate": _repeat_is_identical(
                AGGREGATE_INTLIB,
                schlib_paths=(aggregate_schlib,),
                pcblib_paths=(aggregate_pcblib,),
            ),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return manifest


def main() -> None:
    manifest = create_intlibs()
    builds = cast(dict[str, dict[str, object]], manifest["builds"])
    multi_source = builds["multi_source"]
    aggregate = builds["aggregate"]
    print(f"Components: {multi_source['component_count']}")
    print(
        "Multi-source streams:",
        len(cast(list[str], multi_source["stream_paths"])),
    )
    print("Aggregate streams:", len(cast(list[str], aggregate["stream_paths"])))
    print(f"Equivalent component graphs: {manifest['component_graphs_match']}")
    print(f"Wrote manifest: {_sample_relative(MANIFEST_PATH)}")


if __name__ == "__main__":
    main()
