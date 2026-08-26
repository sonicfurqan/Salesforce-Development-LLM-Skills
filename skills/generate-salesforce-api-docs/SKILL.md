---
name: generate-salesforce-api-docs
description: "Use this skill to generate a static, single-page Swagger/OpenAPI-style HTML reference documenting this Salesforce org's integrations, built by default entirely from local source: one tab for outbound API calls (Apex callouts and Flow HTTP actions this org makes to external systems) and one tab for inbound REST resources (@RestResource Apex classes exposed to external callers), each with its HTTP method, endpoint/URL mapping, and example request/response JSON reverse-engineered from the Apex wrapper classes involved. Trigger this whenever the user wants API documentation, an integration reference, a Swagger-style page, or asks things like 'document our APIs', 'generate/refresh the API docs', 'what REST endpoints do we expose', 'list our outbound callouts with sample payloads', or 'give me a reference page for our Mulesoft/external integrations' — even if they don't say 'Swagger' explicitly. By default this skill only reads local repo metadata and never calls a live org. It supports an optional 'check org' mode — trigger phrases like 'check org', 'query the org', 'pull live metadata', 'refresh from the org', or 'make sure this matches what's actually deployed' — where it retrieves fresh Apex/Flow/Named Credential metadata directly from the org into a scratch folder before analyzing, then cleans up after itself. This skill does not retrieve or deploy metadata as a standalone action (use platform-metadata-retrieve / platform-metadata-deploy for that)."
metadata:
  version: "1.1"
  domains: ["Platform", "Developer Experience", "Documentation"]
  relatedSkills:
    - "platform-metadata-retrieve"
    - "generate-packagexml"
  cliTools:
    - tool: ["sf"]
      semver: ">=2.0.0"
---

# generate-salesforce-api-docs

Generates a static, single-page HTML API reference for this org's integrations by reading Apex classes and Flow metadata — by default from the local repo, no org connection required, with an optional check-org mode (Step 0) that pulls a fresh copy from a live org first. The output looks and behaves like a Swagger/OpenAPI page: two tabs (Outbound API Calls, Inbound REST Resources), one card per endpoint, each showing method, endpoint, source class/method, and example request/response JSON.

---

## Scope

- **In scope**: statically analyzing Apex classes and Flows to find outbound HTTP callouts and inbound `@RestResource` endpoints, deriving example request/response JSON from the Apex wrapper/DTO classes those endpoints actually use, and rendering it all into one static HTML file. By default the source is the local repo; optionally (see Step 0) the source can be a fresh pull from a live org.
- **Out of scope**: retrieving or deploying metadata as a standalone action outside of what this skill needs for its own analysis (`platform-metadata-retrieve` / `platform-metadata-deploy` own that), or making any live callout to verify a payload — every example in the output is derived from source code, never from a real request/response. Even in check-org mode, the org is only ever queried for metadata (source code and config), never invoked as an API.

If the local source is stale or incomplete (e.g. the user just made org changes that haven't been pulled) and the user hasn't asked for check-org mode, mention that `platform-metadata-retrieve` or this skill's own check-org mode would give a more current picture, rather than silently documenting a stale snapshot.

---

## Workflow

### 0. (Optional) Check org — pull fresh metadata before analyzing

Skip this step entirely unless the user's request signals they want live-org verification (e.g. "check org", "query the org", "pull live metadata", "refresh from the org", "make sure this matches what's deployed"). Without that signal, go straight to Step 1 against local repo source — this keeps the default behavior fast and side-effect-free.

When check-org mode is requested:

1. **Determine the target org.** Use the org alias/username the user names; otherwise use the CLI's default org (omit `--target-org`). If it's ambiguous which org they mean (e.g. multiple orgs authenticated and none specified), ask rather than guessing.
2. **Retrieve into a scratch folder, not the real source tree.** The retrieved metadata is only a working copy for this doc build, not something to leave lying around in the project or committed to source control. Create a scratch directory inside the project root (required — `sf project retrieve start --output-dir` must be inside the project boundary), e.g. `.api-docs-scratch/`, then:

   ```
   sf project retrieve start --metadata ApexClass --metadata ApexTrigger --metadata Flow --metadata NamedCredential --metadata ExternalCredential --output-dir .api-docs-scratch --target-org <alias> --json
   ```

   Omit `--target-org` to use the default org. This follows the same `sf project retrieve start` patterns as the `platform-metadata-retrieve` skill — use only the Bash tool for this, never an MCP tool.
3. **Analyze the retrieved copy.** Run Steps 1–3 below exactly as normal, but scan `.api-docs-scratch/` (falling back to the local repo tree for anything the retrieve didn't cover, e.g. if a metadata type failed to retrieve). Retrieving `NamedCredential`/`ExternalCredential` here means endpoint constants that route through a Named Credential can be resolved to their real, currently-configured endpoint URL instead of just citing the symbol.
4. **Clean up.** After the HTML is rendered (Step 4) and before reporting the summary, delete `.api-docs-scratch/` (`rm -rf .api-docs-scratch` or equivalent). Leaving retrieved org metadata sitting in the repo risks it getting accidentally committed and drifting stale on the next run.
5. **Fail soft.** If `sf project retrieve start` errors (org not authenticated, metadata type unavailable, etc.), report the error, fall back to local-source analysis for the parts that failed, and say clearly in the summary which parts came from the org versus local source.

### 1. Find outbound API calls (this org calling out)

Search Apex for callout evidence:

- Classes/methods with `Database.AllowsCallouts` or `@future(callout=true)`
- `new Http()` paired with `.send(`, or `HttpRequest`/`HttpResponse` usage
- `req.setEndpoint(...)` — resolve the endpoint string; if it points to a constant, Custom Metadata field, Named Credential (`callout:MyCredential/...`), or custom setting rather than a literal, follow the reference and note the resolved value plus its source (e.g. `callout:Mulesoft_Endpoint (ZXL_StaticConstants.MULESOFTENDPOINT)`), since these are almost never inline strings in practice
- `req.setMethod(...)` for the HTTP verb

Search Flows (`**/*.flow-meta.xml`) for `<actionCalls>` invoking External Services or HTTP Callout actions, and `<apexPluginCalls>` — each is one more outbound entry with its own inputs/outputs.

For each callout site, trace the **body**: find what's passed to `req.setBody(JSON.serialize(x))` (or an equivalent), then read that Apex type's fields to build the request JSON shape. Trace the **response**: find where `response.getBody()` is deserialized (`JSON.deserialize(body, SomeWrapper.class)`) and use that wrapper's fields for the response JSON shape. If the response is only inspected by status code and never deserialized, say so in the card instead of inventing a body.

### 2. Find inbound REST resources (external callers hitting this org)

Search Apex for `@RestResource(urlMapping='...')` classes. For each, list every annotated method (`@HttpGet`, `@HttpPost`, `@HttpPut`, `@HttpPatch`, `@HttpDelete`) with that class's `urlMapping`.

For the **request** shape: find how the method reads input — `RestContext.request.requestBody` deserialized into a wrapper class, or typed method parameters that Salesforce auto-binds from JSON — and use that type's fields. For the **response** shape: find what's written to `RestContext.response.responseBody` or simply returned from the method (Salesforce auto-serializes the return value) and use that type's fields.

### 3. Derive example JSON from each wrapper/DTO class found in steps 1–2

Build one illustrative example object per wrapper class using its declared fields and types — not real business data:

- `String` → a short descriptive placeholder (e.g. `"PROMO-1000"` for a field named `promotionCode`, not `"string"`) — infer plausible content from the field name when it's obvious, otherwise use a generic sample
- `Boolean` → `true`, `Integer`/`Decimal` → a small round number, `Date`/`Datetime` → an ISO-8601 example
- `List<T>` → an array with one representative element
- A nested wrapper type → a nested object, recursed the same way
- A field typed as `Object`, `Map<String,Object>`, or built via untyped `JSON.serializePretty`/manual string concatenation → mark it in the card as `"// shape not statically determinable"` rather than guessing at keys that don't exist in code

### 4. Render the HTML

Copy [assets/template.html](assets/template.html) to the output path (default `api-list/index.html`; create the `api-list/` folder if missing). Replace the `API_DATA` object in the copied file's `<script>` block with the discovered entries — the template's structure and rendering/search/tab JS should not need edits, only the data. See the template's inline comments for the exact shape of each entry (`method`, `endpoint`/`urlMapping`, `source`, `description`, `requestExample`, `responseExample`, `notes`).

### 5. Report a summary

Tell the user the counts (e.g. "4 outbound callouts, 2 inbound REST resources"), whether the doc was built from local source or from a live org check (and which org), and flag anything notable: callouts whose body/response shape couldn't be resolved, endpoints resolved through a Named Credential/constant, or Flow-based callouts (these are easy to miss and worth calling out explicitly).

---

## Rules / Constraints

Run this skill only when explicitly invoked by the user, not automatically on every request.

| Constraint                                                                                            | Rationale                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Regenerate `api-list/index.html` fully rather than hand-editing it if it already exists               | The file is a derived artifact of current source; patching it piecemeal risks stale or duplicate entries drifting from what the code actually does                                            |
| Never fabricate an endpoint URL, field, or example value that isn't backed by something in the source | This is a reference developers will trust when building against these integrations — a plausible-looking but wrong example is worse than an explicit "shape not statically determinable" note |
| Never make a live callout or org query to "verify" a payload                                          | Out of scope by design (see Scope) — this is a static-analysis doc generator, not an integration test, even in check-org mode                                                                 |
| Resolve endpoint constants/Named Credentials to their actual value, but still cite the source symbol  | A reader needs both the real endpoint and where to go change it                                                                                                                               |
| Check-org mode is opt-in only — never retrieve from an org unless the user's request signals it       | Querying an org is a network call with real latency/auth requirements; most doc requests just want the fast local-source pass                                                                 |
| Check-org retrieves go to a scratch folder and are deleted after the HTML is rendered                 | The retrieval is a means to an end (fresher analysis input), not something meant to persist in or be committed to the repo                                                                    |

---

## Reference File Index

| File                   | When to read                                                                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `assets/template.html` | The output template — copy it to the target path and replace only the `API_DATA` block; read its inline comments for the exact entry shape expected by the renderer |
