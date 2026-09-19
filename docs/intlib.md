# IntLib

`AltiumIntLib` reads existing Altium integrated libraries and creates them from
ordered prepared source libraries.

## Create an IntLib

Prepare and validate the source libraries first, then package their exact bytes:

```python
from altium_monkey import AltiumIntLib

result = AltiumIntLib.create_from_libraries(
    "passives.IntLib",
    schlib_paths=["prepared/Resistors.SchLib", "prepared/Capacitors.SchLib"],
    pcblib_paths=["prepared/Metric.PcbLib", "prepared/Imperial.PcbLib"],
)
print(result.component_count, result.output_sha256)
for source in result.sources:
    print(source.stream_path, source.sha256)
for warning in result.warnings:
    print(warning.code, warning.subject)
```

The method derives all cross-reference and parameter metadata. It supports
shared and alternate PCBLIB footprint choices, requires exactly one current
choice when a component has choices, preserves embedded PcbLib assets, and
reports unused footprints as warnings. Existing destinations require
`overwrite=True`.

Compiler-owned component fields are derived by the writer. A redundant source
`Comment` of `=Value` or `Description` equal to the symbol description is
canonicalized; conflicting reserved source parameters are rejected.

The writer requires at least one SchLib and permits a model-free build with no
PcbLib. Input order controls `SchLib/<n>.schlib` and `PCBLib/<n>.pcblib`
numbering. Component and footprint names must be globally unique across their
respective input lists. It does not merge libraries, apply catalogs, accept
caller-authored metadata streams, package a separate PCB3DLib, or support
non-PCBLIB model types. It adds no arbitrary component-count or package-size
caps. Creation is deterministic and cross-platform.

## Read and Extract

Use the reader to:

1. list component and model metadata from `LibCrossRef.Txt`
2. find embedded `.SchLib`, `.PcbLib`, and `.PCB3DLib` source streams
3. extract source streams to normal files
4. write a simple `.LibPkg` referencing extracted sources
5. split extracted SchLib/PcbLib files with their normal library APIs

Some vendor-generated libraries contain extractable source streams but malformed
cross-reference metadata. `AltiumIntLib` still opens those files for source
recovery. Check `component_parse_error` when metadata availability matters:

```python
from altium_monkey import AltiumIntLib

with AltiumIntLib("vendor.IntLib") as intlib:
    if intlib.component_parse_error:
        print(f"Component metadata unavailable: {intlib.component_parse_error}")
    intlib.extract_sources("extracted_sources")
```

## Examples

Start with:

1. [`intlib_create_from_libraries`](../examples/intlib_create_from_libraries/README.md)
2. [`intlib_extract_sources`](../examples/intlib_extract_sources/README.md)

See [SchLib](schlib.md) and [PcbLib](pcblib.md) for preparing or working with
source libraries.
