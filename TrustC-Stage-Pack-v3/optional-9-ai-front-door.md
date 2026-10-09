# Optional Stage 9 — Plain English to TrustSpec

## When to do this

Only after Stage 8 works. This extension is useful to the Generative AI story but must not delay or replace the deterministic core. It is outside the eight-stage MVP acceptance criteria.

## Scope

Implement `trustc from-text description.txt -o proposed.trust` using one explicitly configured provider (Claude or Gemini) and its currently documented API. Consult that provider's official docs at implementation time and lock its SDK. Credentials come from the user's environment and are never included in prompts, generated source or logs.

The model returns TrustSpec text only. Parse and verify it deterministically. Show the proposed spec, diagnostics and public/exposure declarations for review. Do not automatically build, start a server, test arbitrary code, or change a failing policy to public merely to pass checks. Provider unavailability must not affect the existing CLI/UI offline workflow.

## Tasks and gates

1. Define provider adapter, timeout, maximum input/output limits and sanitized failure result. No hidden retries with unrelated data or unbounded cost.
2. Supply the exact supported grammar and examples to the model; never invent unsupported roles/relations/enum syntax.
3. Validate model output using the same parser/rules. Treat description and returned text as data, not operational instructions.
4. Write proposed output to a new file, preserving existing files unless replacement was explicitly requested. CLI exit is 0 only for accepted proposal, 1 for verifier errors, 2 for syntax/reference errors, 3 for provider execution failure.
5. Tests cover valid output, syntax error, wrong ownership/public policy, credential exposure, malicious prompt text, oversized output, provider timeout and absent key. Test adapters may be mocked; a real provider smoke is separate and never labelled executed when credentials are unavailable.
6. UI integration, if added, shows draft state and requires explicit application of the proposal. Update contracts/schema version deliberately if adding HTTP routes.

Completion record must distinguish structural acceptance from correct intent. “The model produced a valid spec” never means “the model correctly understood every access policy.”

## v3 handoff

Use prompts/09-OPTIONAL-AI.md only when this extension is selected. Save offline versus live evidence separately and rerun affected core gates. Update the final review archive; provider smoke may remain NOT RUN and must not be represented as a completed live integration.
