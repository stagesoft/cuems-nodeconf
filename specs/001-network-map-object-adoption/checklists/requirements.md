# Specification Quality Checklist: Network-map object adoption and the Avahi vocabulary cutover

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-07
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

Passed on the first iteration. Three items warrant an explicit note rather than a
silent tick, because a literal reading would fail them and the reading would be wrong:

1. **"No implementation details" / "no implementation details leak"** — the spec names
   no class, method, module, file or line number, and states every requirement as a
   behaviour. It does name domain artifacts: `network_map.xml`, the Avahi TXT record,
   the response shape `{'OK': bool, 'error'?: str}`, and the template filenames. Those
   are not implementation choices this feature is free to make — they are contracts with
   other components and with a live UI. Suppressing them would make the requirements
   untestable. Recorded as a deliberate scoping of the rule, not an exemption from it.

2. **"Written for non-technical stakeholders"** — the stakeholders for a node-discovery
   daemon are operators and maintainers. The user stories are written in their terms
   (adding a node in the settings view, nodes finding each other, upgrading a node
   safely) and the requirements below them are written for whoever implements. No
   requirement assumes familiarity with this repository's internals.

3. **"Success criteria are technology-agnostic"** — SC-004 and SC-007 reference a TXT
   record key and a package installation. Both are the subject matter, not the technology
   chosen to satisfy the criterion.

Two further observations for the next phase:

- **SC-003 and SC-006 cannot be satisfied by the test suite.** Avahi and zeroconf
  behaviour here is characterized against mocks; nothing in the suite exercises real mDNS,
  D-Bus or multi-node discovery. Both criteria require verification on the live controller.
  The plan must say how, or record the manual procedure honestly — the constitution's
  testing gate requires one or the other, and treats silence as a failure.

- **SC-006 and SC-007 depend on a counterpart repository** whose half of the cutover is
  planned but not yet executed. They are gates on the merge, not on this repository's
  work reaching a testable state.

The clarification the flow document expected to force — what the RPC returns in each of
the three failure cases once the error strings are gone from the callee — is already
answered by FR-010 and User Story 1's scenarios 2 through 4. `/speckit-clarify` should
find nothing new there.

## Post-analysis remediation (2026-09-15)

`/speckit-analyze` found eleven issues across spec/plan/tasks, none CRITICAL. All were
remediated; the checklist above still passes. Two changed requirement text and are worth
naming here, since a reader of an earlier revision would have acted differently:

- **FR-012 was internally inconsistent with the plan** and the analysis pass did not catch
  it — the requirement mandated *repairing* `cleanup()` by assigning a collaborator during
  initialisation, while research D-C had already established that the method has no callers
  and that repairing it would make `settings.xml` a construction-time requirement of the
  daemon. FR-012 now requires removal. Found while applying the other fixes.
- **FR-016 assigned template-file renaming to this repository**, which ships no templates.
  It now constrains only the *resolution* of template names here, and states its dependency
  on `cuems-common`'s file rename landing in the same window.

Also: the `cleanup()` edge case was dropped (deleting the method removes the case), the
deliberate "master" survivals are now recorded as exemptions rather than left to look like
oversights, and three coverage gaps became tasks (T042 the merge gate, T052 the permissions
inspection, T053 the scope-boundary check).
