# ADR-035: User-Managed AI Credentials

## Status

Proposed

## Context

RAC is evolving as a product knowledge infrastructure platform.

Current capabilities focus on:

- Structured knowledge artifacts
- Repository intelligence
- Relationship management
- Portfolio analysis
- Workflow automation

Future roadmap items may introduce AI-assisted capabilities, including:

- Artifact generation
- Artifact improvement
- Repository analysis
- Knowledge synthesis
- Interactive guidance through Explorer and future extensions

As AI functionality expands, RAC requires a clear architectural position regarding:

- Model providers
- Credential management
- Inference costs
- Infrastructure ownership

Without a defined approach, RAC risks becoming dependent on:

- Centralized hosted services
- Vendor-specific implementations
- Maintainer-funded inference
- Operational infrastructure unrelated to its core purpose

RAC's primary value lies in managing and understanding product knowledge.

Inference should remain a replaceable dependency rather than a core responsibility.

## Decision

RAC shall adopt a user-managed AI credential model by default.

Users shall provide and manage credentials for supported AI providers.

RAC shall:

- Orchestrate AI workflows
- Provide repository and artifact context
- Manage prompts and interactions
- Process model responses

RAC shall not require a RAC-operated inference service.

Users shall remain responsible for:

- Provider selection
- Credential management
- Model selection
- Inference costs

## Principles

### Principle 1 — Provider Agnostic Integration

AI capabilities shall be designed around provider abstraction rather than provider dependence.

Supported providers may include:

- OpenAI
- Anthropic
- Google Gemini
- Ollama
- Future local or hosted providers

No provider shall become a mandatory dependency for RAC.

### Principle 2 — RAC Owns Context, Not Inference

RAC's responsibility is to provide:

- Artifact context
- Repository context
- Relationship context
- Workflow orchestration

AI providers are responsible for:

- Model execution
- Token processing
- Response generation

This separation preserves clear ownership boundaries.

### Principle 3 — No Mandatory RAC Cloud Dependency

Users should be able to access AI-assisted capabilities without depending on RAC-operated infrastructure.

For example:

```bash
rac improve requirements.md
```

should remain possible using a user-selected provider and user-managed credentials.

RAC should not require requests to pass through RAC-owned services.

### Principle 4 — Support Local Execution

The architecture should support local and self-hosted models where practical.

Examples may include:

- Ollama
- Local LLM runtimes
- Enterprise-hosted inference endpoints

This preserves deployment flexibility and reduces vendor lock-in.

### Principle 5 — AI Remains Optional

RAC functionality shall not assume the presence of AI capabilities.

Core repository intelligence should remain available without requiring:

- AI providers
- API keys
- Network connectivity

AI should enhance workflows rather than define them.

## Rationale

RAC's long-term value lies in:

- Structured knowledge management
- Repository intelligence
- Traceability
- Product understanding

These capabilities remain valuable regardless of which AI provider is used.

By treating AI as an integration layer rather than a platform dependency, RAC can:

- Remain open and extensible
- Support multiple providers
- Avoid infrastructure costs
- Adapt to future model ecosystems

This approach aligns with previous architectural decisions that favour interoperability and separation of concerns.

## Consequences

### Positive

- No inference costs for RAC maintainers.
- Reduced operational complexity.
- Provider flexibility for users.
- Lower security and compliance burden.
- Support for local and self-hosted models.
- Reduced vendor lock-in.
- Strong alignment with open-source distribution.

### Additional Benefits

- New providers can be added without architectural change.
- Enterprise environments can use approved internal providers.
- AI integrations remain modular and replaceable.

### Negative

- Additional setup required for users.
- Different providers may produce different results.
- Provider integrations require ongoing maintenance.
- Documentation complexity may increase as providers are added.

## Risks

There is a risk that future AI features assume the availability of a specific provider.

This may lead to:

- Vendor lock-in
- Provider-specific workflows
- Reduced portability
- Increased maintenance burden

Contributors introducing AI functionality should ask:

> Could this capability operate with a different provider or a local model?

If the answer is no, the implementation may be too tightly coupled to a specific AI ecosystem.

## Alternatives Considered

### RAC-Hosted AI Service

Operate a RAC-managed service that performs inference on behalf of users.

#### Pros

- Simplified user experience.
- Consistent model behaviour.

#### Cons

- Ongoing operational costs.
- Infrastructure ownership.
- Security and compliance responsibilities.
- Increased complexity.
- Potential monetisation pressure.

### Single Provider Integration

Standardise on a specific AI provider.

#### Pros

- Simplified implementation.
- Predictable outputs.

#### Cons

- Vendor lock-in.
- Reduced flexibility.
- Provider-specific roadmap dependency.

### User-Managed AI Credentials (Selected)

Users manage credentials and provider selection while RAC manages context and orchestration.

#### Pros

- Lowest operational burden.
- Maximum flexibility.
- Strong alignment with open-source principles.
- Supports local and hosted models equally.

## Relationship to Other ADRs

### ADR-012 — Repository Intelligence as the Value Layer

ADR-012 establishes repository intelligence as RAC's primary source of value.

ADR-029 ensures inference remains external while repository intelligence remains internal.

### ADR-013 — Leverage Existing Source Control Systems

ADR-013 positions Git as an external infrastructure dependency.

ADR-029 applies a similar principle to AI providers.

### ADR-014 — Viewer-Agnostic Knowledge Artifacts

ADR-014 promotes independence from specific presentation layers.

ADR-029 promotes independence from specific AI providers.

### ADR-015 — Explorer as a Consumer

ADR-015 defines Explorer as a consumer of RAC capabilities.

AI-assisted Explorer functionality should therefore consume RAC intelligence and user-selected AI providers rather than implement inference logic directly.

## Future Considerations

This decision applies to RAC Core and open-source RAC extensions.

It does not prohibit future commercial offerings from providing:

- Managed AI services
- Hosted inference
- Enterprise integrations
- Value-added cloud capabilities

Such offerings should remain additive and should not invalidate the user-managed model supported by RAC Core.

## Success Measures

Evidence that this decision is succeeding may include:

- AI features work across multiple providers.
- Local models are supported where practical.
- RAC operates without requiring hosted inference.
- New AI integrations reuse common abstractions.
- Users retain control over credentials and provider selection.

## Review Date

Review at v1.0.0 or upon introduction of the first AI-assisted capability within RAC Core.
