# intlib_create_from_libraries

Create the same small, realistic IC integrated library in two ways:

1. Package seven ordered SchLib files and seven ordered PcbLib files directly.
2. Merge those inputs into one SchLib and one PcbLib before packaging them.

The example uses real library assets shipped with the examples. Its component
subset includes an i.MX RT device, EEPROM, flash memory, two related
protection-device variants, and two resistor variants derived from the shipped
`R_2P.Schlib`. The resistors share the shipped
`R0603_0.55MM_MD.PcbLib` footprint while their value and part-number parameters
differ. The two protection devices also share a footprint, and one has an
alternate footprint. The subset keeps one unused footprint to demonstrate the
writer's typed warning.

Both IntLibs are reopened and checked for the same component-to-footprint graph.
Every embedded source is compared with its prepared input by SHA-256, and each
build is repeated to demonstrate byte-for-byte determinism.

The writer uses a pinned, cross-platform form of Altium's Windows en-US
component ordering. Creating and reading these IntLibs does not require Windows
or an Altium installation.

## What It Shows

- Ordered multi-SchLib and multi-PcbLib packaging
- A merged aggregate that produces the same component graph
- Multi-part schematic symbols and small single-symbol libraries
- Default, alternate, and shared footprint links
- Five embedded 3D model payloads retained through both packaging styles
- Parameter variation across related component records
- Reuse of one generic resistor symbol and footprint for two parameter variants
- Punctuation-sensitive component names (`SM712-02HTG` and `SM712.TCT`)
- Exact source preservation, deterministic output, and unused-footprint warnings

## Run

From the package root:

```powershell
uv run python examples\intlib_create_from_libraries\intlib_create_from_libraries.py
```

## Main Output

```text
examples/intlib_create_from_libraries/output/ic-subset-multi-source.IntLib
examples/intlib_create_from_libraries/output/ic-subset-aggregate.IntLib
examples/intlib_create_from_libraries/output/prepared/multi_source/
examples/intlib_create_from_libraries/output/prepared/aggregate/
examples/intlib_create_from_libraries/output/intlib_create_manifest.json
```
