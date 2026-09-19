# PrjPcb

`AltiumPrjPcb` is the public container for Altium project files. Use it when
you need to inspect or mutate an existing `.PrjPcb`, work with project
parameters and variants, resolve project documents, or run an associated
OutJob.

Use it when you need to:

1. read schematic, PCB, library, and OutJob document references
2. add or replace project document entries
3. set, get, or delete project parameters
4. create or select a project variant
5. resolve reachable SchDoc and PcbDoc paths
6. run the project-associated OutJob through `prj.outjob().run(...)`
7. inspect or set project class-generation policy used by Altium ECO flows

## Project Parameters

Project parameters belong in the `.PrjPcb`, not in the schematic document. This
matters for title blocks and dynamic templates that use Altium parameter
expressions such as `=PROJECT_TITLE`, `=PCB_PART_NUMBER`, or `=VariantName`.

Use:

```python
prj = AltiumPrjPcb("project.PrjPcb")
prj.set_parameter("PROJECT_TITLE", "Example Project")
prj.set_parameters({"PCB_PART_NUMBER": "WN-001", "PCB_CODENAME": "demo"})
value = prj.get_parameter("PROJECT_TITLE")
prj.delete_parameter("OLD_PARAMETER")
prj.save("project.PrjPcb")
```

## Variants

Use `add_variant(...)` and `set_current_variant(...)` for the project-level
variant state that Altium uses for project context and special-string
substitution.

```python
prj.add_variant("A", current=True)
assert prj.get_current_variant() == "A"
```

`AltiumPrjPcb.variants` parses existing `ProjectVariantN` sections, including
raw variation rows, DNP/not-fitted designators, variant-level parameter rows,
per-designator `ParamVariation` rows, grouped parameter overrides, and the
variant unique id / fabrication flag.

`add_variant(...)` creates or updates an empty project variant. It does not
author component-level fitted/not-fitted rows or alternate-part rows.

`AltiumDesign` applies variant parameter overrides to BOM rows and uses
DNP/not-fitted rows for BOM/PnP variant handling. Alternate fitted component
rows are preserved in raw variant metadata but are not applied as semantic
component replacements yet.

## Documents

Use `add_document(...)` when the document type can be inferred from the suffix.
Use `set_documents_from_directory(...)` when creating or normalizing a project
folder from existing files.

For minimal new projects, `AltiumPrjPcbBuilder` remains an acceptable public
project-file convenience helper. It is not the same as the retired schematic
fluent builders. It only writes project document membership and basic project
configuration.

## Class Generation

`AltiumPrjPcb.class_generation_options` exposes the project-wide
`[PrjClassGen]` policy that controls schematic/user-defined class transfer
during Altium compile/ECO workflows. For schematic differential-pair directives,
`net_class_manual_enabled=True` lets directive `ClassName` and
`DifferentialPairClassName` values transfer into PCB `Classes6/Data`.

```python
from altium_monkey.altium_prjpcb import (
    AltiumPrjPcb,
    AltiumPrjPcbClassGenerationOptions,
)

prj = AltiumPrjPcb("project.PrjPcb")
options = prj.class_generation_options

prj.set_class_generation_options(
    AltiumPrjPcbClassGenerationOptions(
        net_class_manual_enabled=True,
    )
)
prj.save("project.PrjPcb")
```

Per-document class-generation policy is available through
`get_document_class_generation_options(...)` and
`set_document_class_generation_options(...)`. Document lookup accepts a
zero-based document index, project-relative path, or filename.

## OutJobs

Use `prj.outjob()` to resolve the project-associated OutJob and run it through
the high-level runner:

```python
prj = AltiumPrjPcb("project.PrjPcb")
result = prj.outjob().run(timeout_seconds=300)
```

The runner launches Altium Designer, runs the OutJob, and waits for the script
completion marker. Altium may remain open after the run completes. The marker
does not prove that Altium produced any output files; callers must verify every
required artifact.

This runner uses Altium's scripting API and is currently reliable only for the
folder-based `GeneratedFiles` manufacturing workflows exercised by the project.
PDF/Publish containers, schematic or PCB prints, and Draftsman output can
silently produce no files on current Altium versions. Mixed-media OutJobs are
not fully iterated.

Altium's SDK guidance requires the OutJob to be one of the project's logical
documents. A sibling `.OutJob` that is absent from the `.PrjPcb` can return a
clean script marker without generating anything. Run against a disposable
project copy and keep its project-bound OutJob identity:

```python
prj = AltiumPrjPcb("working-copy/project.PrjPcb")
result = prj.outjob().run(
    timeout_seconds=300,
    stage_outjob_copy=False,
)
if not expected_gerber.exists():
    raise RuntimeError("Altium returned without generating the expected Gerber")
```

Use Altium's OutJob editor or Project Releaser for PDF/document outputs and for
native orchestration across all configured output containers. See the
[README limitation](../README.md#known-outjob-automation-limitation) and the
[`outjob_runner` example](../examples/outjob_runner/README.md).

## Use With Care

Direct edits to low-level `.PrjPcb` INI sections are sometimes useful for
preserving unusual Altium project settings, but use the public parameter,
variant, document, and OutJob helpers when they exist.

Do not encode machine-specific absolute paths in project documents. Keep
project document references project-relative when creating public examples or
redistributable assets.

## Examples

Start with:

1. [`prjpcb_make_project`](../examples/prjpcb_make_project/README.md)
2. [`outjob_runner`](../examples/outjob_runner/README.md)
3. [`schdoc_apply_dynamic_template`](../examples/schdoc_apply_dynamic_template/README.md)
4. [`hello_altium_design`](../examples/hello_altium_design/README.md)

See [AltiumDesign](altium_design.md) for project-level analysis and generated
JSON contracts.
