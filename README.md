# Salesforce Development Skills

This repository contains reusable Salesforce-focused Copilot skills and a small CLI to install them into a project.

The goal is to make it easy to share and reuse Salesforce developer workflows across repos and assistants without copying skill files manually. Each skill is stored as a `SKILL.md` file and can be pulled into a project’s local skills directory for use by Copilot or similar tooling.

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

## How it works

This repo includes a CLI that installs a skill from a GitHub repository into the first valid skills directory it finds in your project:

1. `.github/skills`
2. `.copilot/skills`
3. `.cloud/skills`

If none exist, it creates `.github/skills` automatically.

## Usage

From this repository, run:

```bash
npm run skill:pull -- pull <github-url> <skill-name>
```

Optional flags:

```bash
npm run skill:pull -- pull <github-url> <skill-name> --target <path> --overwrite
```

- `--target` lets you force the destination folder
- `--overwrite` replaces an existing skill in the target directory

## Example: copy a skill into your project

If you want to install one of the skills from this repo into another Salesforce project, run a command like this:

```bash
npm run skill:pull -- pull https://github.com/your-org/salesforce-development-skills generate-package-xml --target .github/skills --overwrite
```

This will copy the `generate-package-xml` skill into your project’s `.github/skills` folder so it is available to your assistant and tooling.

You can also install the API docs skill the same way:

```bash
npm run skill:pull -- pull https://github.com/your-org/salesforce-development-skills generate-salesforce-api-docs --target .github/skills --overwrite
```

## Example from this repo

If you are using this repo directly and want to install one of its bundled skills into a project folder from the command line:

```bash
cd /path/to/your/project
npm install
npx skill-pull --help
```

Or, if the project already has this repo wired as a local CLI tool, use:

```bash
npm run skill:pull -- pull https://github.com/your-org/salesforce-development-skills generate-package-xml
```

## Notes

- This project is designed for Salesforce development workflows and org metadata automation.
- The CLI is intentionally lightweight and repository-driven.
- Skills are installed by reading the target repo, locating `SKILL.md`, and copying it to the project’s skills folder.

## License

MIT

