import zipfile

from scripts.make_release import build_release


def test_release_package_excludes_sensitive_files(tmp_path):
    output, included, skipped = build_release(tmp_path)
    assert output.exists()
    assert included > 0
    assert skipped > 0

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())

    assert ".env" not in names
    assert ".env.example" in names
    assert "Portal_Corporativo.zip" not in names
    assert all(not name.startswith("logs/") for name in names)
    assert all(not name.endswith((".db", ".bak", ".log", ".xlsx", ".xls", ".pdf")) for name in names)
    assert all("__pycache__" not in name for name in names)
