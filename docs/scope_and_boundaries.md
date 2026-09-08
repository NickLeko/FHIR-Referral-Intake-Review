# Scope And Boundaries

## In scope

- Mock FHIR bundle ingestion and narrow live R4 reference assembly
- SMART Backend Services client credentials against a public sandbox
- Additive Task disposition delivery after human review, with local outbox recovery
- Intake support for a small fixed set of FHIR resources
- Independent read-only reference-integrity measurement across standard R4 types
- Deterministic extraction into an administrative review packet
- Missing, ambiguous, and unsupported element detection
- Explicit HITL review before finalizing the handoff summary
- Saved reviewed output artifacts

## Out of scope

- Interactive SMART EHR launch
- Authenticated reviewer identity and production authorization
- Production referral management workflows
- Broad FHIR resource coverage in intake packet parsing
- Clinical recommendations
- Diagnosis or treatment suggestions
- Autonomous operational decisions

## Why this is admin workflow support

The artifact is centered on referral or order intake review. It transforms structured data into a packet that an administrative reviewer can inspect, not a system that makes clinical judgments. The output is a handoff summary for downstream operational handling, such as scheduling or follow-up on missing intake elements.

## Why human review is required

Administrative intake quality often depends on context, not just field presence. Even when data is structured, ambiguous service descriptions, unclear requester identity, or incomplete supporting context still require human confirmation. This prototype makes that boundary explicit rather than hiding it.

## Limitations

- Intake extraction supports only a small subset of resource fields
- Resource relationships are handled with simple reference resolution
- Ambiguity detection is rule-based and intentionally bounded
- Local reviewed JSON keeps its existing contract; live reviews also create Tasks on the source sandbox
- No source-version concurrency guard, competing-review reconciliation, or full FHIR conformance
- See [integration details and limitations](integration.md)

## Non-production disclaimer

The [reference-integrity validator](reference_integrity.md) uses R4 schema
metadata to inventory references across resource types independently of packet
assembly. It leaves the seven intake inputs, reviewed-output contract, and
human gate unchanged. Its sample statistics describe one public sandbox at
the recorded time; they are not production prevalence or full FHIR validation.

This repository is a portfolio-grade integration artifact using synthetic and public-sandbox data. It is meant to demonstrate healthcare interoperability literacy, auditability, and HITL workflow design. It is not a production system and should not be used for live patient care or operational decision-making.

**Verification boundary:** Token acquisition with granted write scope, conditional Task create, read-back, and sequential replay were confirmed live, as was the dangling-Patient 410. Lost responses, injected 500s, rate limiting (429), expiry between read/write, and partial batch failure are mock-tested only. **Concurrent uniqueness is unverified: no live or mocked concurrency test exists.**
