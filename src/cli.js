#!/usr/bin/env node

const path = require("node:path");
const { installSkillFromGithub } = require("./index.js");

function looksLikeGithubUrl(value) {
    return typeof value === "string" && /github\.com\//i.test(value);
}

function parseArgs(argv) {
    const args = {
        command: "",
        repoUrl: "",
        skillName: "",
        targetDir: process.cwd(),
        overwrite: false
    };

    if (argv.length === 0) {
        return args;
    }

    if (looksLikeGithubUrl(argv[0])) {
        args.command = "pull";
        args.repoUrl = argv[0];
        args.skillName = argv[1] || "";
    } else {
        args.command = argv[0];
        args.repoUrl = argv[1] || "";
        args.skillName = argv[2] || "";
    }

    for (let i = 0; i < argv.length; i += 1) {
        const token = argv[i];

        if (token === "--overwrite") {
            args.overwrite = true;
            continue;
        }

        if (token === "--target") {
            args.targetDir = path.resolve(argv[i + 1] || process.cwd());
            i += 1;
            continue;
        }
    }

    return args;
}

function printHelp() {
    console.log("Usage: salesforce-skills pull <github-url> <skill-name> [--target <path>] [--overwrite]");
}

function main() {
    const args = parseArgs(process.argv.slice(2));

    if (!args.command || args.command === "help" || args.command === "--help") {
        printHelp();
        process.exit(0);
    }

    if (args.command !== "pull") {
        console.error(`Unknown command: ${args.command}`);
        printHelp();
        process.exit(1);
    }

    if (!args.repoUrl || !args.skillName) {
        printHelp();
        process.exit(1);
    }

    const result = installSkillFromGithub({
        repoUrl: args.repoUrl,
        skillName: args.skillName,
        targetDir: args.targetDir,
        overwrite: args.overwrite
    });

    console.log(`Installed '${result.skill}' from ${result.repo}`);
    console.log(`Copied to: ${result.outputDir}`);
}

main();
