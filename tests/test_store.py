from datetime import timedelta

from jobalert.store import SeenStore, now_kst


def test_mark_and_persist(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.mark("wanted:1", score=88.0, title="서비스 기획자")
    store.save()

    reloaded = SeenStore(path)
    assert reloaded.is_seen("wanted:1")
    assert reloaded.entries["wanted:1"]["score"] == 88.0


def test_prune_drops_old_entries(tmp_path):
    store = SeenStore(tmp_path / "seen.json", keep_days=30)
    store.entries["old"] = {"notified_at": (now_kst() - timedelta(days=60)).isoformat()}
    store.entries["new"] = {"notified_at": now_kst().isoformat()}
    assert store.prune() == 1
    assert "new" in store.entries and "old" not in store.entries


def test_corrupt_state_file_is_ignored(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{ not json", encoding="utf-8")
    assert SeenStore(path).entries == {}
