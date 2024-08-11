import re
import subprocess
import tomllib
from pathlib import Path
from typing import List, Sequence

import urllib3
from packaging.requirements import Requirement
from packaging.version import Version


def main():
    pyproject_path = Path(__file__).parent / "pyproject.toml"
    pyproject = load_pyproject(pyproject_path)

    all_versions = fetch_all_versions()
    current_version = get_current_version(pyproject)
    target_versions = [v for v in all_versions if v > current_version]

    for version in target_versions:
        paths = update_files_with_version(version)
        if has_uncommitted_changes():
            commit_changes(paths, version)
        else:
            print(f"No changes for version {version}")


def load_pyproject(pyproject_path: Path) -> dict:
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def fetch_all_versions() -> List[Version]:
    http = urllib3.PoolManager()
    response = http.request("GET", "https://pypi.org/pypi/ruff/json")
    if response.status != 200:
        raise RuntimeError("Failed to fetch versions from PyPI")

    releases = response.data.decode("utf-8")
    versions = [Version(release) for release in releases.get("releases", [])]
    return sorted(versions)


def get_current_version(pyproject: dict) -> Version:
    dependencies = pyproject.get("project", {}).get("dependencies", [])
    requirement = next(
        (r for r in map(Requirement, dependencies) if r.name == "ruff"), None
    )

    if not requirement:
        raise ValueError("pyproject.toml does not have 'ruff' as a dependency")

    specifier = requirement.specifier
    if len(specifier) != 1 or specifier[0].operator != "==":
        raise ValueError(f"'ruff' specifier should be exact matching, found: {specifier}")

    return Version(specifier[0].version)


def update_files_with_version(version: Version) -> Sequence[str]:
    def replace_pyproject_toml(content: str) -> str:
        return re.sub(r'"ruff==.*"', f'"ruff=={version}"', content)

    def replace_readme_md(content: str) -> str:
        content = re.sub(r"rev: v\d+\.\d+\.\d+", f"rev: v{version}", content)
        return re.sub(r"/ruff/\d+\.\d+\.\d+\.svg", f"/ruff/{version}.svg", content)

    paths = {
        "pyproject.toml": replace_pyproject_toml,
        "README.md": replace_readme_md,
    }

    updated_paths = []
    for path, replacer in paths.items():
        update_file(Path(path), replacer)
        updated_paths.append(path)

    return tuple(updated_paths)


def update_file(path: Path, replacer: typing.Callable[[str], str]) -> None:
    with open(path, "r+", encoding="utf-8") as f:
        content = f.read()
        new_content = replacer(content)
        f.seek(0)
        f.write(new_content)
        f.truncate()


def has_uncommitted_changes() -> bool:
    return bool(subprocess.check_output(["git", "status", "-s"]).strip())


def commit_changes(paths: Sequence[str], version: Version) -> None:
    subprocess.run(["git", "add", *paths], check=True)
    subprocess.run(["git", "commit", "-m", f"Mirror: {version}"], check=True)
    subprocess.run(["git", "tag", f"v{version}"], check=True)


if __name__ == "__main__":
    main()
