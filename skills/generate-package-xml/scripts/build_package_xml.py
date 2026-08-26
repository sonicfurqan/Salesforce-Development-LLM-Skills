#!/usr/bin/env python3
"""
Builds a Salesforce package.xml manifest from live org metadata.

Wraps `sf org list metadata-types` and `sf org list metadata` so that the
whole "list types -> list members per type -> filter -> assemble XML" flow
is one deterministic step instead of several ad hoc CLI calls threaded
through JSON parsing by hand.

Subcommands:
  list-types   Print every metadata type xmlName enabled in the org (one per
               line), so a caller can confirm a type name or pick types
               interactively before running `build`.
  build        Resolve members for the requested type(s), apply an optional
               prefix filter, optionally pull in metadata those members
               reference, and write package.xml.

Performance: each `sf` invocation pays a fixed CLI startup cost (usually
1-3s) on top of the actual API call, and that cost is what dominates when
resolving hundreds of metadata types (e.g. `--types ALL`). Since these calls
are I/O-bound (waiting on the CLI subprocess / network, not CPU), they are
run concurrently via a thread pool (--max-workers, default 8) rather than
one type at a time. Progress is streamed to stderr as each type/chunk
finishes so a long `ALL` run isn't silent.

`--types DEFAULT` resolves to a curated set of the metadata types most
commonly involved in an application's customizations (Apex, LWC/Aura,
objects/fields, page layouts/FlexiPages, validation rules, permission
sets/profiles, tabs, apps, reports/dashboards — see DEFAULT_TYPES below).
It exists so a scoped build doesn't have to enumerate every metadata type
in the org (slow) or have the caller hand-type the same ~15 type names
every time. `--types ALL` still does a full org-wide scan when needed.

Examples:
  python build_package_xml.py list-types --org my-org
  python build_package_xml.py build --types ApexClass,CustomObject --org my-org
  python build_package_xml.py build --types DEFAULT --prefix ZXL_ --org my-org
  python build_package_xml.py build --types ALL --prefix ZXL_ --org my-org
  python build_package_xml.py build --types Report,Dashboard --org my-org \
      --output manifest/package.xml
  python build_package_xml.py build --types ApexClass --prefix ZXL_ \
      --no-dependencies --org my-org
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.dom import minidom

# Metadata types that require a --folder value per listMetadata call. The
# xmlName used to list the *folders themselves* differs from the member
# type's own name (confirmed against the Metadata API Folder reference —
# it is not derivable from `sf org list metadata-types` output).
FOLDER_TYPE_MAP = {
    "Report": "ReportFolder",
    "Dashboard": "DashboardFolder",
    "Document": "DocumentFolder",
    "EmailTemplate": "EmailFolder",
}

# RefMetadataComponentType values that MetadataComponentDependency can
# return but that are not real, independently-retrievable package.xml
# types (standard objects, the package itself, etc). Pulling these in
# would either fail the retrieve/deploy or add noise, so they're dropped
# and reported in the summary instead of silently vanishing. Confirmed
# live: a dependency on the standard User object comes back with
# RefMetadataComponentType "User", which (like StandardEntity) never
# appears in `sf org list metadata-types` — it isn't a real package.xml
# type name, so writing <types><name>User</name>... would be invalid.
DEPENDENCY_SKIP_TYPES = {
    "StandardEntity",
    "InstalledPackage",
    "System",
    "User",
}

# Some metadata types are "child" components whose real package.xml
# member name must be qualified with their parent (CustomField as
# Object.Field, Layout as Object-LayoutName, RecordType as
# Object.RecordTypeName, etc). MetadataComponentDependency mostly returns
# these already qualified (confirmed for CustomField), but not always —
# a live test surfaced a RecordType dependency returned as the bare name
# "RecordType" with no object qualifier, which is not a valid, retrievable
# manifest entry on its own (Salesforce's dependency graph can report this
# for generic/master record-type usage that isn't tied to one specific
# custom record type). Rather than write a malformed member and let it
# fail at retrieve/deploy time, names for these types that don't look
# qualified are dropped and counted in the summary instead.
DEPENDENCY_QUALIFIED_SEPARATOR = {
    "CustomField": ".",
    "RecordType": ".",
    "ValidationRule": ".",
    "WorkflowRule": ".",
    "BusinessProcess": ".",
    "CompactLayout": ".",
    "WebLink": ".",
    "Layout": "-",
}

# Curated set of metadata types that cover the bulk of what a typical
# application customization touches. Used when the caller passes
# `--types DEFAULT` instead of enumerating every type in the org — a full
# `ALL` scan is usually overkill (and much slower) when the goal is "give
# me a manifest of our custom stuff", not a complete org backup. Every
# name below was confirmed listable via `sf org list metadata` (a couple,
# like ValidationRule, are child types that don't appear in
# `sf org list metadata-types` output but are still directly listable).
#
# Deliberately excludes "CustomSetting" — it isn't a real, independently
# listable metadata type (confirmed live: `sf org list metadata
# --metadata-type CustomSetting` errors with INVALID_TYPE). Custom
# Settings are defined as CustomObject records under the hood, so they're
# already covered by the CustomObject entry below.
DEFAULT_TYPES = [
    "ApexClass",
    "ApexTrigger",
    "LightningComponentBundle",
    "AuraDefinitionBundle",
    "CustomObject",
    "CustomField",
    "CustomMetadata",
    "FlexiPage",
    "Layout",
    "ValidationRule",
    "PermissionSet",
    "Profile",
    "CustomTab",
    "CustomApplication",
    "Report",
    "Dashboard",
]

# Chunk size for MetadataComponentId IN (...) SOQL clauses used when
# resolving dependencies. MetadataComponentDependency only supports
# filtering by Id (confirmed live — filtering by MetadataComponentName
# raises INVALID_FIELD), so this chunks fixed-length 18-char record ids
# rather than member names. That also sidesteps the Windows `cmd.exe`
# ~8191-char command-line limit that long/many member names could blow
# past — 200 ids is ~4KB even with quoting, comfortably under both that
# and the Tooling API's own SOQL length limit.
DEPENDENCY_ID_CHUNK_SIZE = 200

PACKAGE_XMLNS = "http://soap.sforce.com/2006/04/metadata"


def run_sf_json(args):
    """Run an `sf` command with --json and return the parsed `result` value."""
    cmd = ["sf"] + args + ["--json"]
    # On Windows, `sf` is a .cmd shim — CreateProcess can't launch it
    # directly without going through a shell.
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=(os.name == "nt"))
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Command failed to return JSON: {' '.join(cmd)}\n{proc.stderr or proc.stdout}"
        )
    if payload.get("status") != 0:
        raise RuntimeError(
            f"sf command error ({' '.join(cmd)}): {payload.get('message', payload)}"
        )
    return payload.get("result")


def as_list(result):
    """`sf org list metadata` returns a dict for a single match, a list for
    multiple, and null/omitted for zero. Normalize to a list."""
    if result is None:
        return []
    if isinstance(result, dict):
        return [result]
    return result


def org_flags(org):
    return ["--target-org", org] if org else []


def list_all_types(org, api_version):
    args = ["org", "list", "metadata-types"] + org_flags(org)
    if api_version:
        args += ["--api-version", api_version]
    result = run_sf_json(args) or {}
    return result.get("metadataObjects", [])


def list_members(metadata_type, org, api_version, folder=None):
    args = ["org", "list", "metadata", "--metadata-type", metadata_type] + org_flags(org)
    if api_version:
        args += ["--api-version", api_version]
    if folder:
        args += ["--folder", folder]
    return as_list(run_sf_json(args))


def resolve_members(metadata_type, org, api_version, warnings, max_workers):
    """Return (sorted_names, id_map) for one metadata type, handling
    folder-based types by listing folders first (in parallel, since a busy
    org can have hundreds of report/document folders).

    id_map maps fullName -> the org-assigned record id from listMetadata's
    response, which dependency resolution later needs (MetadataComponentDependency
    can only be filtered by id, not by name). A handful of types/records
    (observed: some Data Cloud DLM object types) come back with a blank id —
    those members are still included in the manifest, they just can't be
    used as a starting point for dependency lookups."""
    folder_type = FOLDER_TYPE_MAP.get(metadata_type)
    if not folder_type:
        try:
            items = list_members(metadata_type, org, api_version)
        except RuntimeError as e:
            warnings.append(f"Skipped {metadata_type}: {e}")
            return [], {}
        id_map = {i["fullName"]: (i.get("id") or None) for i in items if i.get("fullName")}
        return sorted(id_map), id_map

    # Folder-based type: enumerate folders, then list members inside each.
    try:
        folders = list_members(folder_type, org, api_version)
    except RuntimeError as e:
        warnings.append(f"Skipped {metadata_type} (could not list {folder_type}): {e}")
        return [], {}

    folder_names = [f.get("fullName") for f in folders if f.get("fullName")]
    id_map = {}

    def fetch_folder(folder_name):
        return folder_name, list_members(metadata_type, org, api_version, folder=folder_name)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(folder_names) or 1)) as executor:
        futures = {executor.submit(fetch_folder, fn): fn for fn in folder_names}
        for future in as_completed(futures):
            folder_name = futures[future]
            try:
                _, items = future.result()
            except RuntimeError as e:
                warnings.append(f"Skipped folder {folder_name} for {metadata_type}: {e}")
                continue
            for i in items:
                name = i.get("fullName")
                if name:
                    id_map[name] = i.get("id") or None
    return sorted(id_map), id_map


def apply_prefix(names, prefix):
    if not prefix:
        return names
    # Folder members come back as "FolderName/ItemName" — filter on the
    # item's own name, not the folder path, so a prefix like "ZXL_" still
    # matches "Shared Reports/ZXL_MonthlyRecap". Matching is case-insensitive
    # since Salesforce naming prefixes are conventionally typed consistently
    # by a team but not enforced by the platform — a user typing "zxl_" or
    # "ZXL_" should get the same result either way.
    prefix_lower = prefix.lower()
    return [n for n in names if n.rsplit("/", 1)[-1].lower().startswith(prefix_lower)]


def read_default_api_version():
    project_file = Path("sfdx-project.json")
    if project_file.exists():
        try:
            data = json.loads(project_file.read_text())
            return data.get("sourceApiVersion")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def query_dependencies_by_ids(ids, org, api_version, warnings):
    """Query the Tooling API's MetadataComponentDependency object for what
    the given component ids reference. Chunked to stay well under both the
    Tooling API's SOQL length limit and the Windows cmd.exe command-line
    limit; a chunk that errors is warned about and skipped rather than
    failing the whole build."""
    records = []
    for i in range(0, len(ids), DEPENDENCY_ID_CHUNK_SIZE):
        chunk = ids[i : i + DEPENDENCY_ID_CHUNK_SIZE]
        quoted = ",".join("'" + cid + "'" for cid in chunk)
        soql = (
            "SELECT RefMetadataComponentType, RefMetadataComponentName "
            f"FROM MetadataComponentDependency WHERE MetadataComponentId IN ({quoted})"
        )
        args = ["data", "query", "--use-tooling-api", "--query", soql] + org_flags(org)
        if api_version:
            args += ["--api-version", api_version]
        try:
            result = run_sf_json(args) or {}
        except RuntimeError as e:
            warnings.append(f"Dependency lookup failed for a batch of {len(chunk)} component(s): {e}")
            continue
        records.extend(result.get("records", []))
    return records


def resolve_dependencies(types_to_members, types_to_ids, org, api_version, depth, max_workers, warnings):
    """Follow references from the already-selected members outward, up to
    `depth` hops. Returns (added, skipped_ref_types, unqualified_counts):
      - added: type name -> set of newly-discovered member names (not
        already present in types_to_members)
      - skipped_ref_types: set of non-retrievable RefMetadataComponentType
        values that were dropped entirely (e.g. StandardEntity, User)
      - unqualified_counts: type name -> count of references dropped
        because the name came back unqualified for a type that requires a
        parent-qualified member name (see DEPENDENCY_QUALIFIED_SEPARATOR)

    Dependency lookups only need a component's id, not its type — so
    unlike member resolution, all ids across all types are queried
    together each hop rather than grouped per type."""
    added = {}
    known = {t: set(m) for t, m in types_to_members.items()}
    unqualified_counts = {}

    frontier_ids = []
    no_id_count = 0
    for id_map in types_to_ids.values():
        for cid in id_map.values():
            if cid:
                frontier_ids.append(cid)
            else:
                no_id_count += 1
    if no_id_count:
        warnings.append(
            f"{no_id_count} member(s) had no org-assigned id in the listing response "
            "(e.g. some Data Cloud object types) and were skipped as a starting point "
            "for dependency lookup — they're still in the manifest"
        )

    skipped_ref_types = set()

    for level in range(depth):
        if not frontier_ids:
            break

        chunks = [
            frontier_ids[i : i + DEPENDENCY_ID_CHUNK_SIZE]
            for i in range(0, len(frontier_ids), DEPENDENCY_ID_CHUNK_SIZE)
        ]
        all_records = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(query_dependencies_by_ids, chunk, org, api_version, warnings): chunk
                for chunk in chunks
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                records = future.result()
                all_records.extend(records)
                print(
                    f"[deps {done}/{len(chunks)}, hop {level + 1}/{depth}] "
                    f"batch: {len(records)} reference(s) found",
                    file=sys.stderr,
                )

        new_names_by_type = {}
        for rec in all_records:
            ref_type = rec.get("RefMetadataComponentType")
            ref_name = rec.get("RefMetadataComponentName")
            if not ref_type or not ref_name:
                continue
            if ref_type in DEPENDENCY_SKIP_TYPES:
                skipped_ref_types.add(ref_type)
                continue
            required_sep = DEPENDENCY_QUALIFIED_SEPARATOR.get(ref_type)
            if required_sep and required_sep not in ref_name:
                unqualified_counts[ref_type] = unqualified_counts.get(ref_type, 0) + 1
                continue
            if ref_name in known.setdefault(ref_type, set()):
                continue
            known[ref_type].add(ref_name)
            added.setdefault(ref_type, set()).add(ref_name)
            new_names_by_type.setdefault(ref_type, set()).add(ref_name)

        if level + 1 >= depth or not new_names_by_type:
            break

        # Continuing another hop needs ids for the newly-discovered
        # members — the dependency query only returned their names/types,
        # so re-list each newly-touched type to pick up ids (only happens
        # when --dependency-depth > 1, which is off by default).
        frontier_ids = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(resolve_members, t, org, api_version, warnings, max_workers): t
                for t in new_names_by_type
            }
            for future in as_completed(futures):
                type_name = futures[future]
                _, id_map = future.result()
                for name in new_names_by_type[type_name]:
                    cid = id_map.get(name)
                    if cid:
                        frontier_ids.append(cid)

    return added, skipped_ref_types, unqualified_counts


def build_package_xml(types_to_members, api_version):
    root = ET.Element("Package", xmlns=PACKAGE_XMLNS)
    for type_name in sorted(types_to_members):
        members = types_to_members[type_name]
        if not members:
            continue
        types_el = ET.SubElement(root, "types")
        for member in members:
            ET.SubElement(types_el, "members").text = member
        ET.SubElement(types_el, "name").text = type_name
    ET.SubElement(root, "version").text = api_version

    rough = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="    ")
    # Drop minidom's own declaration and blank lines, then use the
    # encoding declaration Salesforce-generated manifests use.
    body_lines = [line for line in pretty.split("\n")[1:] if line.strip()]
    return '<?xml version="1.0" encoding="UTF-8" ?>\n' + "\n".join(body_lines) + "\n"


def cmd_list_types(args):
    types = list_all_types(args.org, args.api_version)
    for t in sorted(types, key=lambda o: o["xmlName"]):
        folder_note = " (folder-based)" if t["xmlName"] in FOLDER_TYPE_MAP else ""
        print(f"{t['xmlName']}{folder_note}")


def cmd_build(args):
    api_version = args.api_version or read_default_api_version()
    if not api_version:
        print(
            "No --api-version given and none found in sfdx-project.json. "
            "Pass --api-version explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    requested = args.types.strip().upper()
    if requested == "ALL":
        print("Listing all metadata types enabled in the org...", file=sys.stderr)
        discovered = list_all_types(args.org, api_version)
        type_names = [t["xmlName"] for t in discovered]
        print(
            f"Found {len(type_names)} metadata type(s) — resolving members "
            f"with {args.max_workers} parallel worker(s)...",
            file=sys.stderr,
        )
    elif requested == "DEFAULT":
        type_names = list(DEFAULT_TYPES)
        print(
            f"Using the default {len(type_names)}-type set ({', '.join(type_names)}) — "
            f"resolving members with {args.max_workers} parallel worker(s)...",
            file=sys.stderr,
        )
    else:
        type_names = [t.strip() for t in args.types.split(",") if t.strip()]

    warnings = []
    types_to_members = {}
    types_to_ids = {}
    empty_types = []
    total = len(type_names)
    done = 0

    def worker(type_name):
        type_warnings = []
        names, id_map = resolve_members(type_name, args.org, api_version, type_warnings, args.max_workers)
        return type_name, names, id_map, type_warnings

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(worker, t): t for t in type_names}
        for future in as_completed(futures):
            type_name = futures[future]
            done += 1
            _, names, id_map, type_warnings = future.result()
            warnings.extend(type_warnings)
            members = apply_prefix(names, args.prefix)
            if members:
                types_to_members[type_name] = members
                types_to_ids[type_name] = {n: id_map.get(n) for n in members}
            else:
                empty_types.append(type_name)
            print(f"[{done}/{total}] {type_name}: {len(members)} member(s)", file=sys.stderr)

    if not types_to_members:
        print(
            "No members found for any requested type after filtering - "
            "package.xml was not written.",
            file=sys.stderr,
        )
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
        sys.exit(1)

    dependency_summary = {}
    if args.include_dependencies:
        selected_count = sum(len(m) for m in types_to_members.values())
        print(
            f"Resolving dependencies for {selected_count} selected member(s) "
            f"({args.dependency_depth} hop(s))...",
            file=sys.stderr,
        )
        dep_warnings = []
        added, skipped_ref_types, unqualified_counts = resolve_dependencies(
            types_to_members, types_to_ids, args.org, api_version, args.dependency_depth, args.max_workers, dep_warnings
        )
        for type_name, names in added.items():
            merged = sorted(set(types_to_members.get(type_name, [])) | names)
            types_to_members[type_name] = merged
            if type_name in empty_types:
                empty_types.remove(type_name)
        warnings.extend(dep_warnings)
        if unqualified_counts:
            warnings.append(
                "Dropped references returned without the required parent-qualified name "
                "(so they'd be invalid manifest entries on their own): "
                + ", ".join(f"{t} x{n}" for t, n in sorted(unqualified_counts.items()))
            )
        dependency_summary = {
            "dependenciesAdded": {t: len(n) for t, n in sorted(added.items())},
            "totalDependencyMembers": sum(len(n) for n in added.values()),
            "skippedRefTypes": sorted(skipped_ref_types),
            "skippedUnqualifiedReferences": unqualified_counts,
        }
        print(
            f"Dependency resolution added {dependency_summary['totalDependencyMembers']} "
            f"member(s) across {len(added)} type(s).",
            file=sys.stderr,
        )

    xml_text = build_package_xml(types_to_members, api_version)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_text, encoding="utf-8")

    summary = {
        "output": str(output_path),
        "apiVersion": api_version,
        "prefix": args.prefix or None,
        "typesIncluded": {t: len(m) for t, m in sorted(types_to_members.items())},
        "totalMembers": sum(len(m) for m in types_to_members.values()),
        "typesWithNoMembers": empty_types,
        "warnings": warnings,
        "dependenciesIncluded": args.include_dependencies,
    }
    summary.update(dependency_summary)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    # --org is added to each subparser (not the top-level parser) so it can
    # be passed after the subcommand, e.g. `build --types X --org myorg` —
    # argparse subparsers only recognize flags declared on themselves.
    p_list = sub.add_parser("list-types", help="List metadata types enabled in the org")
    p_list.add_argument("--org", help="Target org alias/username (default org if omitted)")
    p_list.add_argument("--api-version", help="API version to use")
    p_list.set_defaults(func=cmd_list_types)

    p_build = sub.add_parser("build", help="Build package.xml")
    p_build.add_argument("--org", help="Target org alias/username (default org if omitted)")
    p_build.add_argument(
        "--types",
        required=True,
        help="Comma-separated metadata type names, DEFAULT (curated common-types set), or ALL",
    )
    p_build.add_argument("--prefix", help="Only include members whose name starts with this")
    p_build.add_argument("--api-version", help="API version; defaults to sfdx-project.json")
    p_build.add_argument("--output", default="manifest/package.xml", help="Output path")
    p_build.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel `sf` CLI calls for listing members/dependencies (default 8)",
    )
    p_build.add_argument(
        "--include-dependencies",
        dest="include_dependencies",
        action="store_true",
        default=True,
        help="Also include metadata referenced by the selected members (default: on)",
    )
    p_build.add_argument(
        "--no-dependencies",
        dest="include_dependencies",
        action="store_false",
        help="Disable dependency inclusion — only the prefix/type-matched members are written",
    )
    p_build.add_argument(
        "--dependency-depth",
        type=int,
        default=1,
        help="How many hops of references to follow when --include-dependencies is on (default 1)",
    )
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
