# Scope And Boundaries

## In scope

- Mock FHIR bundle ingestion and narrow live R4 reference assembly
- SMART Backend Services client credentials against a public sandbox
- Additive Task disposition delivery after human review, with local outbox recovery
- Support for a small fixed set of FHIR resources
- Deterministic extraction into an administrative review packet
- Missing, ambiguous, and unsupported element detection
- Explicit HITL review before finalizing the handoff summary
- Saved reviewed output artifacts

## Out of scope

- Interactive SMART EHR launch
- Authenticated reviewer identity and production authorization
- Production referral management workflows
- Broad FHIR resource coverage
- Clinical recommendations
- Diagnosis or treatment suggestions
- Autonomous operational decisions

## Why this is admin workflow support

The artifact is centered on referral or order intake review. It transforms structured data into a packet that an administrative reviewer can inspect, not a system that makes clinical judgments. The output is a handoff summary for downstream operational handling, such as scheduling or follow-up on missing intake elements.

## Why human review is required

Administrative intake quality often depends on context, not just field presence. Even when data is structured, ambiguous service descriptions, unclear requester identity, or incomplete supporting context still require human confirmation. This prototype makes that boundary explicit rather than hiding it.

## Limitations

- Only a small subset of resource fields is supported
- Resource relationships are handled with simple reference resolution
- Ambiguity detection is rule-based and intentionally bounded
- Local reviewed JSON keeps its existing contract; live reviews also create Tasks on the source sandbox
- No source-version concurrency guard, competing-review reconciliation, or full FHIR conformance
- See [integration details and limitations](integration.md)

## Non-production disclaimer

This repository is a portfolio-grade integration artifact using synthetic and public-sandbox data. It is meant to demonstrate healthcare interoperability literacy, auditability, and HITL workflow design. It is not a production system and should not be used for live patient care or operational decision-making.
