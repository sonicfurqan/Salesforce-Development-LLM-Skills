const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function isSkillDirectory(directoryPath) {
    return fs.existsSync(path.join(directoryPath, "SKILL.md"));
}

function parseGithubUrl(repoUrl) {
    if (!repoUrl) {
        throw new Error("A GitHub repository URL is required.");
    }

    // Supports both repository URLs and tree URLs.
    const match = repoUrl.match(/github\.com[/:]([^/]+)\/([^/]+?)(?:\.git)?(?:\/tree\/([^/]+)\/(.+))?\/?$/i);
    if (!match) {
        throw new Error(`Unsupported GitHub URL: ${repoUrl}`);
    }

    const owner = match[1];
    const repo = match[2];
    const branch = match[3] || "HEAD";
    const treePath = match[4] || "";

    return {
        owner,
        repo,
        branch,
        treePath,
        cloneUrl: `https://github.com/${owner}/${repo}.git`
    };
}

function normalizeRepoKey(owner, repo) {
    return `${owner}-${repo}`.replace(/[^a-zA-Z0-9._-]/g, "-").toLowerCase();
}

function resolveSkillsBaseDir(targetRepo) {
    const preferredExistingDirs = [
        path.join(targetRepo, ".github", "skills"),
        path.join(targetRepo, ".copilot", "skills"),
        path.join(targetRepo, ".cloud", "skills")
    ];

    for (const baseDir of preferredExistingDirs) {
        if (fs.existsSync(baseDir)) {
            return baseDir;
        }
    }

    return path.join(targetRepo, ".github", "skills");
}

function findSkillDirectories(rootDir, skillName, depth = 0) {
    if (depth > 8) {
        return [];
    }

    const matches = [];
    const entries = fs.readdirSync(rootDir, { withFileTypes: true });
    for (const entry of entries) {
        if (!entry.isDirectory()) {
            continue;
        }

        const absolute = path.join(rootDir, entry.name);
        if (entry.name === ".git" || entry.name === "node_modules") {
            continue;
        }

        if (entry.name === skillName && isSkillDirectory(absolute)) {
            matches.push(absolute);
        }

        matches.push(...findSkillDirectories(absolute, skillName, depth + 1));
    }

    return matches;
}

function copyDirectory(sourceDir, destinationDir, overwrite) {
    if (!fs.existsSync(destinationDir)) {
        fs.mkdirSync(destinationDir, { recursive: true });
    }

    const entries = fs.readdirSync(sourceDir, { withFileTypes: true });
    for (const entry of entries) {
        const fromPath = path.join(sourceDir, entry.name);
        const toPath = path.join(destinationDir, entry.name);

        if (entry.isDirectory()) {
            copyDirectory(fromPath, toPath, overwrite);
            continue;
        }

        if (!overwrite && fs.existsSync(toPath)) {
            continue;
        }

        fs.copyFileSync(fromPath, toPath);
    }
}

function installSkillFromGithub(options = {}) {
    const repoUrl = options.repoUrl || "";
    const skillName = options.skillName || "";
    const overwrite = Boolean(options.overwrite);
    const targetRepo = options.targetDir ? path.resolve(options.targetDir) : process.cwd();

    if (!skillName) {
        throw new Error("A skill name is required.");
    }

    const parsed = parseGithubUrl(repoUrl);
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "copilot-skill-"));

    try {
        childProcess.execFileSync("git", ["clone", "--depth", "1", parsed.cloneUrl, tempDir], {
            stdio: "ignore"
        });

        const directPath = parsed.treePath ? path.join(tempDir, parsed.treePath) : "";
        const candidates = [];

        if (directPath && path.basename(directPath) === skillName && isSkillDirectory(directPath)) {
            candidates.push(directPath);
        }

        candidates.push(...findSkillDirectories(tempDir, skillName));

        if (candidates.length === 0) {
            throw new Error(
                `Skill '${skillName}' was not found in ${repoUrl}. Ensure folder '${skillName}' contains SKILL.md.`
            );
        }

        const sourceDir = candidates[0];
        const repoKey = normalizeRepoKey(parsed.owner, parsed.repo);
        const skillsBaseDir = resolveSkillsBaseDir(targetRepo);
        const destinationDir = path.join(skillsBaseDir, repoKey, skillName);

        copyDirectory(sourceDir, destinationDir, overwrite);

        return {
            sourceDir,
            outputDir: destinationDir,
            baseDir: skillsBaseDir,
            repo: `${parsed.owner}/${parsed.repo}`,
            skill: skillName
        };
    } finally {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
}

module.exports = {
    installSkillFromGithub
};
