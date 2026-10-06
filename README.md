
# Description

A curated list of AI development tools and setup steps for Salesforce projects.

## Ponytail

- Reduce token output costs with [Ponytail](https://github.com/dietrichgebert/ponytail).
- Load the plugin into your coding agent.

## Code Memory MCP

- Use a memory graph to avoid repeatedly searching the codebase.
- Repository: [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
- Install the MCP on your computer. The executable is installed at:
    `%LOCALAPPDATA%\Programs\codebase-memory-mcp\codebase-memory-mcp.exe`
- To view and graph projects, open Command Prompt and run:
    `codebase-memory-mcp --ui=true --port=9749`
- To re-index automatically when code changes, run:
    `codebase-memory-mcp config set auto_index true`
- To register projects manually instead of indexing all projects, run:
    `codebase-memory-mcp config set watcher_enabled false`

## Existing Salesforce Skills

- Use pre-built Salesforce skills to assist with development.
- Reference: [sf-skills](https://github.com/forcedotcom/sf-skills)
- Run `npx skills add forcedotcom/sf-skills` in a terminal and select the skills relevant to your project.
- Avoid installing every skill; unused skills consume tokens.

## What this repo contains

### `generate-package-xml`

Generates a Salesforce `package.xml` manifest from the metadata that exists in a live org. It can filter by metadata type, optional name prefix, and includes common dependency-related metadata to make the manifest more useful for retrieve/deploy workflows.

Use this when you want to:
- build a manifest for a subset of metadata
- generate a package file for custom Salesforce objects, Apex, flows, layouts, etc.
- scope a manifest to a namespace or naming prefix such as `API_` or `MyApp__`

Example prompt:

```text
Generate a package.xml for all custom metadata with the API_ prefix in my default org.
```

Sample output:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>API_AccountTriggerHandler</members>
        <members>API_InvoiceSyncBatch</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>API_Invoice__c</members>
        <name>CustomObject</name>
    </types>
    <version>60.0</version>
</Package>
```

### `generate-salesforce-api-docs`

Creates a static HTML reference page for your org’s outbound API calls and inbound REST resources. It analyzes Apex and Flow metadata, builds example request/response payloads, and produces a Swagger-like page for easier integration documentation.

Use this when you want to:
- document current outbound callouts
- list internal REST endpoints exposed by `@RestResource`
- generate a simple API reference from source code

Example prompt:

```text
Document our Salesforce API integrations and generate a static HTML reference for all outbound callouts and REST endpoints in this repo.
```

Sample output:

```text
Generated API documentation page with 4 outbound callouts and 2 inbound REST resources.
Saved to: api-list/index.html
```


### `generate-code-comments`

Add Apexdoc style code comments to apex and jsstyle type comments to lwc.
comments are kept to minimum as needed bases. it will add unnessery comments to each line. 
by assuming code explains it self. it ads one line to explain logic if it is complex


## Notes

- This project is designed for Salesforce development workflows and org metadata automation.

## License

MIT

