# Publication preparation

## Goal
Prepare a standalone, anonymised Git repository containing all approved scripts,
waveform CSVs, full-data HTML, figures, processed results and alignment exports.
The essay and original Git history are excluded. The source checkout is preserved.

## Phases
1. Inspect source, preserve existing edits, and create a safe baseline: complete.
2. Import approved files, remove identifiers, and make paths portable: complete.
3. Document measurements, schemas, execution and provenance: complete.
4. Validate numerical preservation, reproducibility, UI and privacy: complete.
5. Commit the release and record commit hashes: complete.
6. Create the user-approved public GitHub repository, push main and verify its SHA: complete.

## Errors
The first independent check expected mixed-case Boolean strings; tables use uppercase TRUE/FALSE. Corrected the checker, without changing data. A shell quoting error in an inline helper produced no edits; moved the helper to a script file.

Additional observations: generated diagram Unicode subscripts were absent from the system font; replaced the two labels with mathtext and verified the PNG. Browser file navigation and an outside-root screenshot destination were rejected by the automation tool; used local HTTP and the allowed tool-output directory, then moved temporary outputs outside the source checkout.

Publication commit: `d61eaea782b96a0a59f07ddba897c65f0d9ccfcf`. All reachable text Git objects and anonymous commit identities passed the post-commit audit.
