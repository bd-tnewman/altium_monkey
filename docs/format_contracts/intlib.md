# IntLib Contract

`AltiumIntLib` is the public reader and narrow prepared-library writer for
Altium integrated libraries.

## Stable Surface

- Open `.IntLib` files as compound library containers.
- List and extract embedded schematic, PCB, and model source entries.
- Parse component and model metadata when the source metadata is valid.
- Create an IntLib from one or more ordered prepared SchLib files and zero or
  more ordered prepared PcbLib files with
  `AltiumIntLib.create_from_libraries(...)`.
- Receive typed build counts, source and output hashes, and warnings through
  `IntLibBuildResult`, `IntLibBuildSource`, and `IntLibBuildWarning`.

The writer derives metadata from immutable source-byte snapshots, validates the
component-to-footprint graph, preserves every source payload exactly, reopens
and validates a staged package, and publishes it transactionally. It supports
PCBLIB implementations, shared footprints, alternate footprints, and embedded
assets already owned by prepared PcbLib files. Input sequence defines source
stream numbering; component and footprint identities remain globally unique.

## Boundary

Library merging, catalog selection, parameter enrichment, PCB3DLib streams,
non-PCBLIB models, bytes/logical-name inputs, ambiguity overrides, and
caller-authored metadata streams remain outside the first writer contract.
Unused footprints are preserved and reported as typed warnings. Compiler-owned
component fields are derived by the writer. A redundant source `Comment` of
`=Value` or `Description` equal to the symbol description is canonicalized;
conflicting reserved source parameters are rejected. Existing outputs are not
replaced unless `overwrite=True`.

The writer enforces observed format and semantic boundaries, but it does not
impose arbitrary component-count or package-size policy caps. Its pinned CP1252
en-US word-sort implementation is deterministic and cross-platform; Altium is
not required to create or reopen a package through the Python API.

The writer emits the governed `0x02` + zlib stream envelope. The reader accepts
both observed envelopes for the exact `LibCrossRef.Txt` and
`Parameters   .bin` metadata paths: `0x00` followed by raw payload bytes and
`0x02` followed by zlib data. `Version.Txt` is never envelope-decoded, and
`0x00` is not generalized to embedded source streams. Unknown wrappers on the
two enveloped metadata streams fail deterministically; opaque non-metadata
streams preserve the existing pass-through behavior. `decompress=False`
always returns the exact stored bytes.

`AltiumIntLib(...)` and `AltiumIntLib.from_file(...)` accept the optional
keyword-only `max_decompressed_stream_bytes` limit. It defaults to 256 MiB and
applies independently to each zlib-decoded stream reached by parsing, direct
reads, or extraction. The limit is not an aggregate extraction or package-size
cap. It must be a positive integer less than the running Python platform's
`sys.maxsize`; invalid values fail before the IntLib is opened.
Writer pre-publication validation derives its internal bound from the already
captured source and generated metadata sizes, so the public reader default
does not become an arbitrary writer input-size policy.

## Test Gates

The contract is covered by focused writer tests, extraction and exact-source
hash checks, deterministic repeat builds, transactional failure injection,
boundary tests, native Altium-reader evidence, realistic public examples, and
release signoff.
