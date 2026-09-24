"""Putting a backup back.

Taking a backup, verifying it and pruning it were all possible from the screen; putting
one back was a file operation done by hand with the server stopped. So the feature these
cover is the other half of the one that already existed - and the half that decides
whether the first half was ever worth anything.

**These tests really do restore.** They replace the catalog and the dataset files of the
running test instance, which is every other test's world as well. So the whole module
works to one protocol: take a backup of the way things are, do the restore being tested,
then restore the first backup to put everything back. The final restore is in a fixture's
teardown rather than at the end of each test, so it happens even when a test fails
halfway.

That protocol only holds because the accounts and the signing key are identical in both
backups - restoring either leaves the session cookies of the test clients valid. A test
that added a user before taking its backup would break the ones that run after it, which
is the sharper version of a mistake already made once in test_backup.
"""

import shutil

import duckdb
import pytest
from app.config import settings
from app.db import catalog
from app.services import backup, restore


@pytest.fixture(scope="module")
def safety(admin, editor, viewer, dataset):
    """A backup of the way things are, restored again when the module is finished.

    Every session-scoped fixture is requested, not only the ones these tests use, and
    that is the whole of a mistake this made once. The snapshot has to contain the world
    the other test files expect to find; taken before `viewer` and `editor` existed, the
    teardown restore deleted those two accounts and every permission test that ran
    afterwards failed on a cookie for a user who was no longer there. Under pytest's
    alphabetical order it passed, because test_backup happened to run first - which is
    the worst kind of green.
    """
    before = backup.run(include_originals=True)
    assert before["verified"], before["errors"]
    yield before
    result = restore.run(before["name"], actor_note="test teardown")
    assert result["ok"], result
    backup.delete(before["name"])


@pytest.fixture
def throwaway(admin):
    """A dataset of its own, so no test here deletes one another test is using."""
    from conftest import wait_for_job

    body = b"plate,make\n1,KIA\n2,MAZDA\n3,KIA\n"
    r = admin.post(
        "/api/datasets/upload", files={"file": ("restore.csv", body, "text/csv")}
    )
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


# ---- the plan, which changes nothing ---------------------------------------------------


def test_the_plan_names_what_would_disappear(admin, safety, throwaway):
    """The dataset exists now and is not in the backup, so restoring loses it. A restore
    that did not say this before asking would be asking for agreement to something the
    person cannot see."""
    plan = restore.plan(safety["name"])
    assert plan["found"]
    removed = {d["dataset_id"] for d in plan["datasets_removed"]}
    assert throwaway in removed, plan["datasets_removed"]
    entry = next(d for d in plan["datasets_removed"] if d["dataset_id"] == throwaway)
    assert entry["rows_now"] == 3
    assert entry["name"] == "restore.csv"


def test_the_plan_touches_nothing(admin, safety, throwaway):
    """It is read in a dialog, possibly several times, by somebody deciding. Reading it
    must not be a step of the thing being decided."""
    before = admin.get("/api/datasets").json()
    restore.plan(safety["name"])
    restore.plan(safety["name"])
    assert admin.get("/api/datasets").json() == before
    assert not (settings.data_dir / restore.STAGING_NAME).exists()


def test_the_plan_says_how_many_accounts_come_back(admin, safety):
    """The catalog is one file: the accounts come back with the dataset list. Somebody
    about to restore a month-old backup needs that number before, not after."""
    plan = restore.plan(safety["name"])
    assert plan["users_in_backup"] == plan["users_now"] == len(catalog.list_users())


def test_a_backup_that_does_not_exist_is_not_a_plan(admin):
    plan = restore.plan("2001-01-01_000000")
    assert plan["found"] is False
    assert plan["blockers"] == ["backup_not_found"]


# ---- what stops it ----------------------------------------------------------------------


def test_an_unverified_backup_is_refused(admin, safety):
    """The one rule that makes the whole feature worth having: a backup nobody read back
    is not restored. Restoring one would be replacing data that works with data nobody
    has checked."""
    manifest = backup.run()
    root = backup.backups_root() / manifest["name"]
    # break it the way a bad disk would: the manifest still promises rows the file has lost
    item = next(i for i in manifest["items"] if i["kind"] == "dataset")
    (root / item["file"]).write_bytes(b"not a database")
    listed = next(b for b in backup.list_all() if b["name"] == manifest["name"])
    assert not listed["intact"]

    try:
        assert "backup_not_verified" in restore.plan(manifest["name"])["blockers"]
        r = admin.post(f"/api/admin/backups/{manifest['name']}/restore")
        assert r.status_code == 409
        assert r.json()["code"] == "restore_not_verified"
    finally:
        backup.delete(manifest["name"])


def test_a_running_job_stops_it(admin, safety, monkeypatch):
    """An import writing into a dataset file about to be renamed away would carry on
    writing into a file nothing points at, and report success."""
    monkeypatch.setattr(catalog, "active_job_count", lambda: 1)
    assert "jobs_running" in restore.plan(safety["name"])["blockers"]
    r = admin.post(f"/api/admin/backups/{safety['name']}/restore")
    assert r.status_code == 409
    assert r.json()["code"] == "restore_jobs_running"


def test_only_an_administrator_may_restore(viewer, editor, safety):
    """Checked through the API rather than by hiding a button."""
    for client in (viewer, editor):
        assert client.get(f"/api/admin/backups/{safety['name']}/restore-plan").status_code == 403
        assert client.post(f"/api/admin/backups/{safety['name']}/restore").status_code == 403


# ---- doing it ---------------------------------------------------------------------------


def test_a_deleted_dataset_comes_back_with_its_rows(admin, safety):
    """The whole feature in one test. A dataset is created, backed up, deleted - the way
    a mistake actually happens - and the backup brings it back with the rows in it, read
    out of the restored file rather than out of a row count."""
    from conftest import wait_for_job

    body = b"plate,make\n1,KIA\n2,MAZDA\n3,KIA\n4,KIA\n"
    r = admin.post("/api/datasets/upload", files={"file": ("gone.csv", body, "text/csv")})
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"

    with_it = backup.run()
    assert with_it["verified"], with_it["errors"]

    admin.delete(f"/api/datasets/{dataset_id}")
    assert admin.get(f"/api/datasets/{dataset_id}").status_code == 404

    try:
        result = restore.run(with_it["name"], actor_note="test")
        assert result["ok"], result

        r = admin.get(f"/api/datasets/{dataset_id}")
        assert r.status_code == 200, "the catalog row did not come back"
        assert r.json()["row_count_raw"] == 4

        r = admin.post(f"/api/datasets/{dataset_id}/data", json={"page": 1, "page_size": 10})
        assert r.status_code == 200, r.text
        assert len(r.json()["rows"]) == 4, "the file came back empty"
    finally:
        backup.delete(with_it["name"])
        admin.delete(f"/api/datasets/{dataset_id}")


def test_what_was_replaced_is_kept_rather_than_deleted(admin, safety, throwaway):
    """A restore is itself destructive - restoring the wrong backup is entirely possible -
    and the state it overwrote is the only copy of right now."""
    before = len(restore.kept_states())
    result = restore.run(safety["name"], actor_note="test")
    assert result["ok"], result

    kept = restore.kept_states()
    assert len(kept) == before + 1
    newest = kept[0]
    assert newest["restored"] == safety["name"]
    assert newest["bytes"] > 0

    # the dataset that the restore removed is still readable in what was set aside
    aside = settings.data_dir / restore.PRE_RESTORE_NAME / newest["name"]
    conn = duckdb.connect(str(aside / "datasets" / f"{throwaway}.duckdb"), read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0] == 3
    finally:
        conn.close()
    restore.delete_kept(newest["name"])


def test_a_restore_leaves_no_staging_behind(admin, safety):
    result = restore.run(safety["name"], actor_note="test")
    assert result["ok"], result
    assert not (settings.data_dir / restore.STAGING_NAME).exists()
    for kept in restore.kept_states():
        restore.delete_kept(kept["name"])


def test_the_flag_is_down_again_afterwards(admin, safety):
    """It gates every endpoint. Left up by a restore that finished, the app would be
    unreachable and nothing would say why."""
    assert not restore.is_active()
    restore.run(safety["name"], actor_note="test")
    assert not restore.is_active()
    assert restore.status()["ok"] is True
    assert admin.get("/api/datasets").status_code == 200
    for kept in restore.kept_states():
        restore.delete_kept(kept["name"])


# ---- the gate ---------------------------------------------------------------------------


def test_every_endpoint_refuses_while_a_restore_is_running(admin, safety):
    """A request arriving mid-swap would reopen the catalog on a file being renamed.

    The refusal carries the stage, which is what lets the screen follow the restore
    without an endpoint that reads the database being replaced.
    """
    restore.begin(safety["name"])
    try:
        for path in ("/api/datasets", "/api/auth/me", "/api/admin/restore/status"):
            r = admin.get(path)
            assert r.status_code == 503, f"{path} answered {r.status_code}"
            assert r.json()["code"] == "maintenance"
            assert r.json()["stage"] == "checking"
            assert r.headers.get("retry-after") == "5"
    finally:
        restore._end(False, "cancelled by test")
    assert admin.get("/api/datasets").status_code == 200


def test_a_second_restore_is_refused_while_one_is_running(admin, safety):
    restore.begin(safety["name"])
    try:
        assert "restore_in_progress" in restore.plan(safety["name"])["blockers"]
    finally:
        restore._end(False, "cancelled by test")


# ---- the staged copy is checked before anything is touched -------------------------------


def test_a_backup_broken_after_verification_fails_before_the_swap(admin, safety, throwaway):
    """The backup verified itself when it was written. This is the second question: that
    the copy landing in staging is still that file. A bad sector between then and now must
    fail while the live data is where it was, not after half of it has been replaced.
    """
    manifest = backup.run()
    assert manifest["verified"], manifest["errors"]
    root = backup.backups_root() / manifest["name"]

    # a database that opens but has lost rows - the failure the manifest can still catch,
    # and the one a file-size check would miss
    item = next(i for i in manifest["items"] if i.get("dataset_id") == throwaway)
    conn = duckdb.connect(str(root / item["file"]))
    conn.execute("DELETE FROM raw_data")
    conn.close()

    try:
        result = restore.run(manifest["name"], actor_note="test")
        assert not result["ok"]
        assert "raw_data" in result["error"], result

        # and the live data is untouched
        r = admin.post(f"/api/datasets/{throwaway}/data", json={"page": 1, "page_size": 10})
        assert r.status_code == 200
        assert len(r.json()["rows"]) == 3
        assert not (settings.data_dir / restore.STAGING_NAME).exists()
        assert not restore.is_active()
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- the screen half ---------------------------------------------------------------------


def test_the_dialog_asks_before_it_acts():
    """A guard: the restore dialog must fetch the plan and hold the confirm button until
    a checkbox is ticked. A restore behind a plain confirm would be a one-click way to
    delete every dataset created since the backup."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "src"
        / "pages"
        / "admin"
        / "settings"
        / "RestoreDialog.tsx"
    ).read_text(encoding="utf-8")
    assert "fetchRestorePlan" in source
    assert "datasets_removed" in source, "the dialog does not show what would disappear"
    assert "disabled={!plan || blocked || !understood}" in source


# ---- a job row that is a corpse ----------------------------------------------------------


def test_a_job_abandoned_long_ago_does_not_block_a_restore_forever(admin, safety):
    """Found by trying it, not by reading it.

    There is no heartbeat: a row says "running" because something set it so, and a
    process killed mid-import leaves it saying that forever. The first restore attempted
    against a real instance was refused by eleven-day-old rows from a session that had
    been killed - and nothing in the interface could have cleared them.
    """
    from datetime import timedelta

    from app.services import clocks

    # a count, not zero: another test file may have left a job of its own behind, and
    # what this is about is whether *this* row is counted
    before = catalog.active_job_count()

    job_id = catalog.create_job("", "import")
    catalog.update_job(job_id, status="running", progress="pretending")

    conn = catalog.get_connection()
    with catalog.db_lock:
        conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            [clocks.now() - timedelta(minutes=catalog.STALE_JOB_MINUTES + 5), job_id],
        )

    try:
        assert catalog.active_job_count() == before, (
            "an abandoned job still counts as running"
        )
    finally:
        catalog.delete_jobs([job_id])


def test_a_job_touched_just_now_does_block_it(admin, safety):
    """The other side of the same window. A live import writing into a dataset file about
    to be renamed away is the failure the blocker exists for, so the window must not be so
    wide that it lets one through."""
    before = catalog.active_job_count()
    job_id = catalog.create_job("", "import")
    catalog.update_job(job_id, status="running", progress="really running")
    try:
        assert catalog.active_job_count() == before + 1
        assert "jobs_running" in restore.plan(safety["name"])["blockers"]
    finally:
        catalog.delete_jobs([job_id])


# ---- a backup brought in from somewhere else --------------------------------------------


def test_a_backup_folder_copied_in_is_listed_and_restorable(admin, safety, tmp_path):
    """The case the whole feature is for: the machine is gone, and what survives is a
    copy of the folder. There is no upload - the folder is put in the backups directory
    and the screen picks it up - so what has to hold is that a backup is identified by
    where it is, not by where it was taken.
    """
    manifest = backup.run()
    assert manifest["verified"], manifest["errors"]
    root = backup.backups_root() / manifest["name"]

    elsewhere = tmp_path / "carried-away"
    shutil.copytree(root, elsewhere)
    shutil.rmtree(root)
    assert manifest["name"] not in {b["name"] for b in backup.list_all()}

    # brought back under a different name, which is what happens when somebody copies a
    # folder and the copy is called "backup (1)" or the date is rewritten by a transfer
    landed = backup.backups_root() / "carried-away"
    shutil.copytree(elsewhere, landed)
    try:
        listed = next(b for b in backup.list_all() if b["name"] == "carried-away")
        assert listed["intact"], "a folder copied in whole was read as damaged"
        plan = restore.plan("carried-away")
        assert plan["found"], plan
        # only the blockers that would be about *this backup* are asserted on: another
        # test file's leftover job row is about the instance, not about whether a folder
        # carried in from elsewhere can be read
        assert "backup_not_found" not in plan["blockers"], plan
        assert "backup_not_verified" not in plan["blockers"], plan
        assert restore.run("carried-away", actor_note="test")["ok"]
    finally:
        backup.delete("carried-away")
        for kept in restore.kept_states():
            restore.delete_kept(kept["name"])


def test_a_backup_is_named_by_its_folder_not_by_its_manifest(admin):
    """The defect that test found. Delete and restore both locate a backup by matching
    folder names; listing it under the name written inside it put a row on the screen
    whose every button answered "no such backup"."""
    manifest = backup.run()
    root = backup.backups_root() / manifest["name"]
    renamed = backup.backups_root() / "renamed-by-hand"
    root.rename(renamed)
    try:
        listed = [b["name"] for b in backup.list_all()]
        assert "renamed-by-hand" in listed
        assert manifest["name"] not in listed
        assert restore.plan("renamed-by-hand")["found"]
    finally:
        backup.delete("renamed-by-hand")
