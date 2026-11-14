# Comments for human and AI maintainers

At a nontrivial boundary, document the **purpose**, **contract**, **invariant**, **rationale**, **failure behavior**, and **test evidence**. A module may cover common context once; local comments should explain the choices that are easy to break during maintenance.

The numerical gate gives a concrete example: NaN is rejected before threshold decisions because ordered comparisons do not behave like ordinary numbers. The comment ties that rationale to a named test. The atomic registry comment explains why capacity is checked before mutation and what is observable before and after replacement.

This convention is inspired by Johnson's [study of expressive code comments](https://doi.org/10.3389/frai.2026.1784973). The study reports model-dependent responses; it does not establish a universal benefit from longer comments. Here, comments are maintained engineering context, and tests provide the behavioral evidence.

Review each change for agreement among code, comments and tests. Remove stale assertions when behavior changes. Treat an unsupported claim in a comment as a defect, even when the program still passes its tests. Research interpretations must remain distinct from implementation contracts.
