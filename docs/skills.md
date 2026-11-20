# Skills

Fifty skill manifests describe small reproducible sequences of read-only tool operations. They are not model prompts that secretly edit source code.

```bash
loopsieve skills list
loopsieve skills show skill-005-assess-release-readiness
loopsieve skills run skill-005-assess-release-readiness
```

Every skill defines a purpose, prerequisites, workflow steps, referenced tools, permissions, outputs, quality gates, failure handling and usage example. The runner executes steps in order and stops at the first unavailable dependency or failed operation. A partially completed workflow reports `PARTIAL` with concrete results and errors.

A skill can be a useful preliminary investigation, but it does not claim to finish a full coding task. For example, the release readiness skill checks whether standard release files exist and inspects Git metadata. It does not publish a release.
