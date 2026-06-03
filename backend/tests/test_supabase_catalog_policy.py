import datetime

import supabase_db


class FakeSupabase:
    def __init__(self):
        self.row = None

    def upsert(self, table, row, *, on_conflict):
        self.row = row
        return [row]


def test_host_app_catalog_flag_uses_timestamp_for_supabase(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(supabase_db, "_sb", lambda: fake)

    supabase_db.upsert_host_app_catalog_flag(
        "production",
        "revelry",
        "quiz",
        {
            "enabled": True,
            "status": "live",
            "capability_overrides": {"can_create_content": True},
        },
    )

    assert isinstance(fake.row["updated_at"], str)
    parsed = datetime.datetime.fromisoformat(fake.row["updated_at"])
    assert parsed.tzinfo is not None
