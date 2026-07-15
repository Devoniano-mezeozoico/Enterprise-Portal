import fnmatch
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release"

EXCLUDE_PATTERNS = (
    ".env",
    ".env.*",
    "*.db",
    "*.db-*",
    "*.sqlite",
    "*.sqlite3",
    "*.bak",
    "*.log",
    "*.zip",
    "*.pyc",
    "__pycache__/*",
    ".pytest_cache/*",
    "venv/*",
    ".venv/*",
    "env/*",
    ".env_dir/*",
    "site-packages/*",
    "logs/*",
    "release/*",
    "dist/*",
    "build/*",
    "static/uploads/*",
    "apps/fiscal/instance/uploads/*",
    "apps/fiscal/instance/results/*",
    "apps/fiscal/RELATORIOS/*",
    "apps/fiscal/269000019290594/*",
    "*.xlsx",
    "*.xls",
    "*.pdf",
)


def should_exclude(relative_path):
    value = relative_path.as_posix()
    if value == ".env.example":
        return False
    parts = value.split("/")
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return True
    return any(fnmatch.fnmatch(value, pattern) for pattern in EXCLUDE_PATTERNS)


def build_release(output_dir=None):
    release_dir = Path(output_dir) if output_dir else RELEASE_DIR
    release_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = release_dir / f"Portal_Corporativo_release_{stamp}.zip"
    included = 0
    skipped = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if should_exclude(relative):
                skipped += 1
                continue
            archive.write(path, relative.as_posix())
            included += 1
    return output, included, skipped


if __name__ == "__main__":
    output, included, skipped = build_release()
    print(f"Release gerado: {output}")
    print(f"Arquivos incluidos: {included}")
    print(f"Arquivos excluidos por seguranca: {skipped}")
    sys.exit(0)
