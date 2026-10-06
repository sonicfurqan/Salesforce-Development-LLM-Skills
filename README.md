
# Descripiton

Curated list of AI devlopment setup to help in development of salesforce project.



## Ponytail
- ponytail to reduce cost of token outputs
- Repo: https://github.com/dietrichgebert/ponytail
- load the plugin into your codeing agent

## Code memory mcp
- memory graph to ovide grep over and over again during search of code
- Repo: https://github.com/DeusData/codebase-memory-mcp
- Instal mcp in your pc
- it installs to \AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe   
- open directory and run "codebase-memory-mcp --ui=true --port=9749" in cmd to view and graph projects
- run "codebase-memory-mcp config set auto_index true" in cmd so that it updates graph on all code change
- run "codebase-memory-mcp config set watcher_enabled false" in cmd if you want to manualy register project to index or else it will index all projects

## Salesforce Existing skill set
- pre built salesforce skill to help in development
- REF : https://github.com/forcedotcom/sf-skills
- run `npx skills add forcedotcom/sf-skills` in terminal and select relevent skills that is need for your projoect.
- NOTE : do not copy all skills as it will consume token if not needed skills are part of your list



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
 
 
## Notes

- This project is designed for Salesforce development workflows and org metadata automation.
 

## License

MIT

