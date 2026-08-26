---
name: generate-package-xml
description: "Use this skill to build a Salesforce package.xml manifest by listing live org metadata and filtering it — by metadata type (a specific type, several types, or every type in the org) and optionally by a name prefix (e.g. 'API_', 'MyApp__'). Trigger this whenever the user wants a package.xml generated, regenerated, or scoped down to a namespace/prefix — including phrases like 'give me a manifest of all our custom stuff', 'package.xml for everything starting with API_', or 'list all ApexClasses/CustomObjects/etc into a manifest'. This skill only builds the manifest file — it does NOT retrieve or deploy metadata; for that, use platform-metadata-retrieve or platform-metadata-deploy instead."
metadata:
  version: "2.0"
  domains: ["Platform", "Developer Experience"]
  relatedSkills:
    - "platform-metadata-retrieve"
  cliTools:
    - tool: ["sf"]
      semver: ">=2.0.0"
---

# generate-package-xml

Builds a `package.xml` manifest from what's actually in a live Salesforce org, filtered by metadata type and (optionally) by a name prefix. It does this by listing the org's metadata via `sf org list metadata-types` / `sf org list metadata`, then assembling the result into a manifest — it does not read or infer from local source files.

By default it also pulls in metadata that the selected members _reference_ (e.g. a matched Apex class's Custom Object/Fields), via a Tooling API dependency lookup, so the manifest is closer to something that will actually deploy cleanly rather than just the members whose names happen to match.

---

## Scope

- **In scope**: discovering metadata types/members from an org, filtering by type and/or name prefix, assembling and writing `package.xml`.
- **Out of scope**: actually retrieving the metadata bodies (`platform-metadata-retrieve`) or deploying (`platform-metadata-deploy`). Once this skill writes the manifest, hand off to `platform-metadata-retrieve` with `--manifest manifest/package.xml` if the user also wants the files pulled down.

---

## Required Inputs

Infer from the user's request; ask only for what's genuinely ambiguous — don't ask about the target org if a default is already configured (see Workflow step 1):

- **Metadata type(s)**: `DEFAULT` (curated common-types set — see Workflow step 2) | `ALL` | one type (e.g. `ApexClass`) | a comma-separated list (e.g. `ApexClass,CustomObject,Flow`). If the user didn't name specific types, start with `DEFAULT` — see Workflow step 2 for when/how to offer the full scan.
- **Prefix filter** (optional): a literal prefix like `API_` or `MyApp__`, applied to the member's own name — not the type name. Matching is case-insensitive (`api_`, `API_`, `Api_` all match the same members), so don't ask the user to confirm casing
- **Target org**: alias/username, if the user names one; otherwise the CLI's default org is used automatically
- **API version** (rarely needed): defaults to `sourceApiVersion` in `sfdx-project.json`
- **Include dependencies** (rarely needed to ask about): on by default — pass `--no-dependencies` only if the user explicitly wants just the raw prefix/type match with nothing pulled in

If the user names a type you're not confident is a valid Salesforce metadata type name, or they want to browse before committing, run `list-types` first (Workflow step 2) rather than guessing.

---

## Workflow

All commands run through the bundled script — don't hand-roll `sf` calls and JSON parsing here. Manually chaining `sf org list metadata-types` -> per-type `sf org list metadata` -> prefix filtering -> XML assembly is exactly the kind of multi-step, error-prone process a script should own: folder-based types (Report/Dashboard/Document/EmailTemplate) need an extra listing pass per folder, single-result JSON responses come back as an object instead of an array, and empty `<types>` blocks are invalid XML — the script already handles all three. It also parallelizes the `sf` calls (each one pays a fixed CLI startup cost, so doing them one at a time is what made `--types ALL` slow) and streams a progress line per type/dependency-chunk to stderr as it goes — surface these lines to the user as they arrive on longer runs rather than going quiet until the final JSON summary.

1. **Confirm the target org.** If the user didn't name one, don't ask — `sf` falls back to the configured default org automatically (omit `--org`).
2. **Decide the type scope:**
   - User named specific type(s) (e.g. "ApexClasses and Flows") → use those exactly.
   - User explicitly asked for everything/every type/a full org scan → use `ALL`.
   - Otherwise (the common case — "give me a manifest of our API\_ stuff", no types named) → use `DEFAULT`. This resolves to a curated ~16-type set covering the bulk of an application customization: `ApexClass`, `ApexTrigger`, `LightningComponentBundle`, `AuraDefinitionBundle`, `CustomObject`, `CustomField`, `CustomMetadata`, `FlexiPage`, `Layout`, `ValidationRule`, `PermissionSet`, `Profile`, `CustomTab`, `CustomApplication`, `Report`, `Dashboard`. It exists so the common request doesn't pay the cost of an org-wide scan (which can be 200+ types) when the user almost always means "our custom application metadata." Note there's deliberately no separate `CustomSetting` entry — confirmed live that it isn't a real listable metadata type (Custom Settings are defined as `CustomObject` records under the hood, so `CustomObject` already covers them); if a user specifically asks for custom settings, that's what to point them to rather than adding `CustomSetting` to a `--types` list.
3. **(Optional) List available types** to validate a type name or let the user pick:
   ```
   python .claude/skills/generate-package-xml/scripts/build_package_xml.py list-types [--org <alias>]
   ```
4. **Build the manifest:**
   ```
   python .claude/skills/generate-package-xml/scripts/build_package_xml.py build \
     --types <DEFAULT|ALL|Type1,Type2,...> \
     [--prefix <prefix>] \
     [--org <alias>] \
     [--output manifest/package.xml] \
     [--no-dependencies] [--dependency-depth 1] [--max-workers 8]
   ```
   Default output is `manifest/package.xml`, created if missing and overwritten if present. Dependency inclusion defaults **on** at depth 1 (see below); pass `--no-dependencies` for a raw prefix/type-only manifest.
5. **After a `DEFAULT`-scoped build finishes, ask the user whether they also want the full org-wide scan** (every metadata type, not just the curated set) — something like: "This manifest covers the common app metadata types (Apex, LWC/Aura, objects/fields, layouts, permission sets, etc.) — want me to scan every metadata type in the org instead, in case something outside that set matches the prefix too? It's slower." If they say no, the `DEFAULT` manifest is the final answer — don't run anything further. If they say yes, rerun step 4 with `--types ALL` (same prefix/org/other flags), which overwrites the manifest with the full-scan result. Skip this ask entirely if the user already named specific types or `ALL` in step 2 — it only applies when you chose `DEFAULT` on their behalf.
6. **Read the JSON summary the script prints** — it reports `typesIncluded` (member count per type), `typesWithNoMembers` (types that matched nothing after filtering, so they were omitted), `warnings` (types or dependency batches skipped due to an `sf` error), and when dependencies were included, `dependenciesAdded` (per-type counts of members pulled in purely because something else referenced them), `totalDependencyMembers`, `skippedRefTypes` (referenced things that aren't real retrievable metadata, e.g. standard objects, and so were dropped entirely), and `skippedUnqualifiedReferences` (per-type counts of references dropped because the org returned them without the parent qualifier their manifest entry needs — see Rules table; a nonzero `CustomField` count here is normal, not an error). Relay this to the user rather than just saying "done" — a silently-dropped type, a 0-member result, or a large dependency addition changing the manifest's scope is easy to miss otherwise.
7. If the script exits non-zero because nothing matched at all, tell the user plainly (wrong prefix, wrong type name, or genuinely nothing in the org) rather than treating it as a generic failure.

### Example

Request: _"generate a package.xml for everything with the API\_ prefix"_ — no specific types named, so this is the `DEFAULT` case:

```
python .claude/skills/generate-package-xml/scripts/build_package_xml.py build --types DEFAULT --prefix API_
```

After this runs, ask the user if they want a full `--types ALL` scan too (Workflow step 5) before considering the request done.

Resulting `manifest/package.xml` shape:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>API_AccountTriggerHandler</members>
        <members>API_DailyExpiredPromoScheduler</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>API_Promotion__c</members>
        <name>CustomObject</name>
    </types>
    <version>66.0</version>
</Package>
```

---

## Rules / Constraints

run this rule only when explicty it is invoked by the user, not automatically on every request. The script is designed to be run directly, and the rules below describe its behavior and limitations.

| Constraint                                                                                                                                                                                          | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Prefix filtering happens client-side, after listing                                                                                                                                                 | The Metadata API's `listMetadata` call has no server-side name filter — the script lists everything of a type, then filters                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Prefix matches the member's own name, not its folder path                                                                                                                                           | For folder-based types a member's `fullName` looks like `Shared Reports/API_MonthlyRecap` — filtering the full string would silently drop everything                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Prefix matching is case-insensitive                                                                                                                                                                 | The platform doesn't enforce naming-prefix casing, so a user typing `api_` shouldn't get zero results just because the org's actual members are `API_`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `--metadata-type` accepts exactly one type per `sf` call                                                                                                                                            | The script loops per type, but runs those calls concurrently (`--max-workers`, default 8) instead of one at a time — each `sf` invocation has a fixed CLI startup cost, and that cost (not the API call itself) is what made a 200+-type `ALL` request slow serially                                                                                                                                                                                                                                                                                                                                                                                                               |
| `--types DEFAULT` is a curated ~16-type set, not a subset the org defines                                                                                                                           | It's hardcoded in the script (`DEFAULT_TYPES`) to the metadata types that make up the bulk of a typical app customization — see Workflow step 2 for the list. It exists so the common "manifest our custom stuff" request doesn't default to an org-wide `ALL` scan, which is both slower and pulls in things (report types, translations, permission set licenses, etc.) that are rarely what's meant by "our stuff"                                                                                                                                                                                                                                                              |
| Report/Dashboard/Document/EmailTemplate need folder enumeration first                                                                                                                               | These are folder-based types; the script lists the corresponding `*Folder` type to get folder names, then lists members per folder (also in parallel)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Types with zero matching members are omitted from the manifest, not written as empty `<types>` blocks                                                                                               | An empty `<types>` block with no `<members>` is invalid in a real deploy/retrieve manifest                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| A metadata type name that the org doesn't recognize is skipped with a warning, not a hard failure                                                                                                   | One bad/mistyped type in a multi-type request shouldn't block the rest from being written                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Dependency inclusion is on by default (1 hop)                                                                                                                                                       | The whole point of filtering by prefix is usually to get a deployable slice — a matched Apex class is much less useful without the Custom Object/Fields it touches. `--no-dependencies` reverts to the raw prefix/type match only                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Dependencies are resolved via the Tooling API's `MetadataComponentDependency` object, filtered by `MetadataComponentId` in batches of ≤200 ids                                                      | This is the org's own record of what references what, rather than trying to statically parse Apex/Flow/etc. source for references, which would be unreliable and miss cross-type cases (e.g. a Flow referencing a Custom Field). Filtering by id rather than name is not optional — confirmed live that `MetadataComponentDependency` rejects `WHERE MetadataComponentName = ...` with `INVALID_FIELD`; the ids come for free from `sf org list metadata`'s response, which already includes an `id` per member alongside `fullName`                                                                                                                                               |
| Dependency-added members are not themselves prefix-filtered                                                                                                                                         | A referenced Custom Object almost never shares your org's custom prefix — filtering it out would defeat the purpose of including it                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `RefMetadataComponentType` values like `StandardEntity` or `User` are dropped, not added as a type                                                                                                  | These aren't real, independently retrievable package.xml types (e.g. a reference to the standard `Account` or `User` object) — confirmed live for `User`, which — like `StandardEntity` — never appears in `sf org list metadata-types`. They're reported in `skippedRefTypes` instead of silently producing an invalid manifest entry                                                                                                                                                                                                                                                                                                                                             |
| References to "child" types (`CustomField`, `RecordType`, `ValidationRule`, `WorkflowRule`, `BusinessProcess`, `CompactLayout`, `WebLink`, `Layout`) are dropped if the name comes back unqualified | Their real package.xml member name must include a parent qualifier (`Object.Field`, `Object-LayoutName`, etc.), but `MetadataComponentDependency` doesn't always return it qualified — confirmed live with a `RecordType` dependency returned as the bare name `RecordType` and a large share of `CustomField` dependencies returned as bare field names with no owning object. Writing those in as-is would produce invalid manifest entries, so they're dropped and counted per type in `skippedUnqualifiedReferences` instead. In practice this means a meaningful chunk of `CustomField` dependencies get dropped, not added — that's expected, not a bug; see Troubleshooting |

---

## Troubleshooting

| Issue                                                                                                                        | Resolution                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `No members found for any requested type after filtering`                                                                    | Prefix or type name likely doesn't match anything in this org — try `list-types` to confirm the type name, or drop the prefix to confirm the type itself has members                                                                                                                                                                                                                                                        |
| A type is missing from the output with a warning like `Skipped <Type>: ...`                                                  | That type name isn't valid for this org/API version, or the org lacks the needed permission — check the type name against `list-types` output                                                                                                                                                                                                                                                                               |
| `No --api-version given and none found in sfdx-project.json`                                                                 | Run from the project root (where `sfdx-project.json` lives) or pass `--api-version` explicitly                                                                                                                                                                                                                                                                                                                              |
| Script can't find `sf` on Windows                                                                                            | Handled internally (the script shells out via `cmd` on Windows since `sf` is a `.cmd` shim) — if it still fails, confirm `sf --version` works in the same terminal                                                                                                                                                                                                                                                          |
| `ALL` with no prefix still takes a while                                                                                     | It's still one `sf` call per metadata type in the org (sometimes 200+), but they now run `--max-workers` at a time (default 8) instead of one at a time — raising `--max-workers` speeds this up further at the cost of more concurrent org load; let the user know before running, or suggest narrowing to specific types first                                                                                            |
| `Dependency lookup failed for a batch of N component(s): ...` warnings                                                       | The org rejected a Tooling API `MetadataComponentDependency` query for that batch (e.g. the user's profile lacks Tooling API access) — those components just don't get dependency expansion; not fatal, and unrelated components are unaffected                                                                                                                                                                             |
| `N member(s) had no org-assigned id ... skipped as a starting point for dependency lookup`                                   | A handful of member types (observed: some Data Cloud DLM object types) come back from `sf org list metadata` with a blank `id`, which dependency lookup needs. Those members are still in the manifest — they just can't seed a dependency search themselves. Not fixable from this script; informational only                                                                                                              |
| `Dropped references returned without the required parent-qualified name ...` warning, especially a large `CustomField` count | Expected, not a bug — `MetadataComponentDependency` doesn't reliably return `CustomField`/`RecordType`/etc. references pre-qualified with their parent object, and writing an unqualified field/record-type name into package.xml would be invalid. See the Rules table; there's currently no reliable way to reconstruct the qualifier from what the query returns, so those references are dropped rather than guessed at |
| Manifest is much bigger than expected after this update                                                                      | Dependency inclusion is on by default now — check the summary's `dependenciesAdded`/`totalDependencyMembers`. Re-run with `--no-dependencies` to get the old prefix-only behavior                                                                                                                                                                                                                                           |

---

## Cross-Skill Integration

| Need                                                        | Delegate to                                                                                          |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Actually retrieve the metadata files listed in the manifest | `platform-metadata-retrieve` skill, e.g. `sf project retrieve start --manifest manifest/package.xml` |
| Deploy metadata using this manifest                         | `platform-metadata-deploy` skill                                                                     |
| List raw metadata types/members without building a manifest | `python .claude/skills/generate-package-xml/scripts/build_package_xml.py list-types`                 |

---

## Reference File Index

| File                           | When to read                                                                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/build_package_xml.py` | The implementation — read it if a request needs behavior the workflow above doesn't cover (e.g. a metadata type with unusual listing requirements) |
