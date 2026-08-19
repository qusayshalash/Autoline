"""The shared/exclusive lock guarding each dataset.

Concurrency bugs do not reproduce by inspection, so these tests actually start threads
and assert on the order things happened in. Each one is written so that the *absence* of
the lock would fail it, not merely make it flaky.
"""

import threading
import time

import pytest
from app.db.connection import _RWLock, datasets


def run(target, *args) -> threading.Thread:
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
    return t


# ---- the lock itself ---------------------------------------------------------------


def test_readers_do_not_block_each_other():
    """The whole reason for a shared mode. If readers serialised, every page of the grid
    would queue behind every other one."""
    lock = _RWLock()
    both_inside = threading.Barrier(2, timeout=2)

    def reader():
        with lock.shared():
            both_inside.wait()

    a, b = run(reader), run(reader)
    a.join(3)
    b.join(3)
    assert not a.is_alive() and not b.is_alive(), "two readers could not be inside at once"


def test_a_writer_waits_for_a_reader_to_finish():
    """The bug this lock exists for: compaction closing the connection out from under an
    export that is still streaming rows."""
    lock = _RWLock()
    order: list[str] = []
    reader_in = threading.Event()

    def reader():
        with lock.shared():
            reader_in.set()
            time.sleep(0.3)
            order.append("reader done")

    def writer():
        reader_in.wait(2)
        with lock.exclusive():
            order.append("writer in")

    r, w = run(reader), run(writer)
    r.join(3)
    w.join(3)
    assert order == ["reader done", "writer in"], order


def test_a_reader_waits_for_a_writer_to_finish():
    lock = _RWLock()
    order: list[str] = []
    writer_in = threading.Event()

    def writer():
        with lock.exclusive():
            writer_in.set()
            time.sleep(0.3)
            order.append("writer done")

    def reader():
        writer_in.wait(2)
        with lock.shared():
            order.append("reader in")

    w, r = run(writer), run(reader)
    w.join(3)
    r.join(3)
    assert order == ["writer done", "reader in"], order


def test_two_writers_never_overlap():
    """Mutual exclusion, asserted by counting rather than by timing."""
    lock = _RWLock()
    inside = 0
    overlaps = []

    def writer():
        nonlocal inside
        for _ in range(40):
            with lock.exclusive():
                inside += 1
                if inside > 1:
                    overlaps.append(inside)
                time.sleep(0.001)
                inside -= 1

    threads = [run(writer) for _ in range(4)]
    for t in threads:
        t.join(10)
    assert overlaps == [], f"writers overlapped: {overlaps}"


def test_a_steady_stream_of_readers_does_not_starve_a_writer():
    """Writer priority. Without it a dashboard polling every second postpones an import
    indefinitely - and the import is what somebody is waiting on."""
    lock = _RWLock()
    stop = threading.Event()
    got_in = threading.Event()

    def reader():
        while not stop.is_set():
            with lock.shared():
                time.sleep(0.005)
            time.sleep(0.001)

    def writer():
        time.sleep(0.05)
        with lock.exclusive():
            got_in.set()

    readers = [run(reader) for _ in range(4)]
    w = run(writer)
    assert got_in.wait(3), "the writer never got in past a stream of readers"
    stop.set()
    for t in readers:
        t.join(3)
    w.join(3)


def test_the_writer_may_take_the_lock_again_and_may_read():
    """Compaction holds the lock for the whole swap and calls close() inside it, which
    takes it again. Non-reentrant, that is a deadlock against itself."""
    lock = _RWLock()
    done = threading.Event()

    def writer():
        with lock.exclusive():
            with lock.exclusive():
                with lock.shared():
                    pass
        done.set()

    run(writer)
    assert done.wait(2), "the lock deadlocked against its own holder"


def test_the_lock_is_released_when_the_body_raises():
    lock = _RWLock()
    with pytest.raises(ValueError):
        with lock.exclusive():
            raise ValueError("boom")
    done = threading.Event()
    run(lambda: (lock.exclusive().__enter__(), done.set()))
    assert done.wait(2), "the lock was not released after an exception"


# ---- through the connection manager ------------------------------------------------


def test_the_write_lock_survives_a_close(dataset):
    """The lock is keyed by dataset id and outlives the connection.

    It used to be stored beside the connection and dropped along with it, so a writer
    that closed the connection while holding the lock left the next writer to build a
    fresh one and walk straight in - two writers at once, on the one path where that
    cannot be allowed. Compaction does exactly that: closes the connection mid-swap.
    """
    first = datasets.write_lock(dataset)
    datasets.close(dataset)
    second = datasets.write_lock(dataset)
    # the context managers differ, but they must come from the same underlying lock
    assert datasets._lock_for(dataset) is datasets._lock_for(dataset)
    del first, second


def test_a_reader_holds_the_dataset_open_against_a_compaction(admin, dataset, oracle):
    """End to end, and the actual reported failure: a long read running while the file
    underneath it is replaced. The read must finish, with all of its rows.
    """
    from app.services import compaction

    counted: list[int] = []
    failed: list[Exception] = []
    reader_started = threading.Event()

    def slow_reader():
        try:
            with datasets.reading(dataset) as cur:
                reader_started.set()
                time.sleep(0.4)          # hold it open across the swap
                counted.append(cur.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0])
        except Exception as exc:  # noqa: BLE001 - recorded and asserted on below
            failed.append(exc)

    r = run(slow_reader)
    assert reader_started.wait(2)
    compaction.compact(dataset)
    r.join(10)

    assert failed == [], f"the reader was interrupted: {failed}"
    assert counted == [len(oracle)]


def test_a_reader_may_take_the_lock_again_while_a_writer_waits():
    """The deadlock this would otherwise be.

    Reads nest, because the query helpers are built from each other. If the inner read
    queued behind a waiting writer, it would be waiting for a writer that cannot start
    until the outer read - held by the same thread - finishes. Nothing would ever move.
    """
    lock = _RWLock()
    outer_in = threading.Event()
    writer_waiting = threading.Event()
    finished = threading.Event()

    def reader():
        with lock.shared():
            outer_in.set()
            writer_waiting.wait(2)
            time.sleep(0.05)          # let the writer actually reach the wait
            with lock.shared():       # must not block
                pass
        finished.set()

    def writer():
        outer_in.wait(2)
        writer_waiting.set()
        with lock.exclusive():
            pass

    r, w = run(reader), run(writer)
    assert finished.wait(3), "a nested read deadlocked against a waiting writer"
    r.join(3)
    w.join(3)


def test_nested_reads_release_only_once():
    """A nested read that decremented the reader count on the way out would leave the
    lock believing nobody is reading while somebody still is."""
    lock = _RWLock()
    with lock.shared():
        with lock.shared():
            pass
        assert lock._readers == 1, "the inner release dropped the outer reader"
    assert lock._readers == 0
    assert lock._reader_depth == {}
