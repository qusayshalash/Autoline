"""Test harness.

Everything here exists to make the tests run against a *real* stack - real DuckDB
files, real HTTP routing, real auth cookies - while touching none of the developer's
actual data. The isolation is done by pointing DATA_DIR at a throwaway directory
before `app.config` is ever imported, since `Settings` reads the environment once at
import time and the catalog/dataset connections derive every path from it.
"""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# ---- isolation, before any app import ----------------------------------------------

def _configured_data_dir() -> Path:
    """Where the app would really keep its data, read before that is overridden below.

    Only the opt-in tests against the developer's own dataset need this, and they cannot
    ask app.config for it - by the time they run, DATA_DIR points at a temp directory. So
    it is resolved here, from the same .env the app reads, and passed along separately.
    """
    env_file = BACKEND / ".env"
    if "DATA_DIR" in os.environ:
        return Path(os.environ["DATA_DIR"])
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATA_DIR=") and not line.startswith("#"):
                return Path(line.split("=", 1)[1].strip())
    return BACKEND / "data"


os.environ["REAL_DATA_DIR"] = str(_configured_data_dir())

_TMP_DATA = Path(tempfile.mkdtemp(prefix="csvstudio-test-data-"))
os.environ["DATA_DIR"] = str(_TMP_DATA)
os.environ["ADMIN_USERNAME"] = "test_admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-pw"

# Hebrew values reach stdout through job-progress prints; on a Windows console that
# defaults to cp1252 those prints raise and would be reported as a test failure in a
# completely unrelated place.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

import synthetic  # noqa: E402

# Guard rail: if the environment override ever stops working, these tests would start
# mutating the real catalog. Better to refuse to run than to find out afterwards.
assert settings.data_dir == _TMP_DATA, (
    f"tests are not isolated: data_dir is {settings.data_dir}, expected {_TMP_DATA}"
)

JOB_TIMEOUT_S = 120


@pytest.fixture(scope="session", autouse=True)
def _cleanup_data_dir():
    yield
    # DuckDB may still hold handles on Windows; a leftover temp directory is a smaller
    # problem than a test run that fails during teardown.
    shutil.rmtree(_TMP_DATA, ignore_errors=True)


@pytest.fixture(scope="session")
def api():
    """The app with startup run: roles seeded, bootstrap admin created."""
    with TestClient(app) as client:
        yield client


def _login(username: str, password: str) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture(scope="session")
def admin(api) -> TestClient:
    return _login("test_admin", "test-admin-pw")


@pytest.fixture(scope="session")
def editor(admin) -> TestClient:
    r = admin.post(
        "/api/users",
        json={"username": "test_editor", "password": "test-editor-pw", "role": "editor"},
    )
    assert r.status_code in (200, 201), r.text
    return _login("test_editor", "test-editor-pw")


@pytest.fixture(scope="session")
def viewer(admin) -> TestClient:
    r = admin.post(
        "/api/users",
        json={"username": "test_viewer", "password": "test-viewer-pw", "role": "viewer"},
    )
    assert r.status_code in (200, 201), r.text
    return _login("test_viewer", "test-viewer-pw")


@pytest.fixture(scope="session")
def anon(api) -> TestClient:
    """No cookie at all - the shape every endpoint must reject."""
    return TestClient(app)


# ---- the synthetic dataset ---------------------------------------------------------


@pytest.fixture(scope="session")
def csv_path() -> Path:
    return synthetic.write(_TMP_DATA / "source" / "synthetic.csv")


@pytest.fixture(scope="session")
def oracle(csv_path) -> list[dict]:
    """What the file contains, according to Python's csv module."""
    return synthetic.read_back(csv_path)


def wait_for_job(client: TestClient, job_id: str, timeout: float = JOB_TIMEOUT_S) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("done", "error"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s; last state: {last}")


@pytest.fixture(scope="session")
def dataset(admin, csv_path) -> str:
    """Uploads and imports the synthetic file through the real HTTP endpoints, so the
    ingestion path under test is the same one the app uses in production."""
    with open(csv_path, "rb") as f:
        r = admin.post(
            "/api/datasets/upload", files={"file": ("synthetic.csv", f, "text/csv")}
        )
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]

    # encoding and delimiter are stated rather than trusted to detection: detection has
    # its own test, and every other test wants a known starting point.
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": synthetic.ENCODING, "delimiter": synthetic.DELIMITER, "has_header": True},
    )
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job

    r = admin.get(f"/api/datasets/{dataset_id}")
    assert r.json()["status"] == "ready", r.text
    return dataset_id
