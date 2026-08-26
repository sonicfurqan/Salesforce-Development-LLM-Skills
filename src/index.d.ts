export interface GithubInstallOptions {
  repoUrl: string;
  skillName: string;
  targetDir?: string;
  overwrite?: boolean;
}

export interface GithubInstallResult {
  sourceDir: string;
  outputDir: string;
  baseDir: string;
  repo: string;
  skill: string;
}

export declare function installSkillFromGithub(options: GithubInstallOptions): GithubInstallResult;
