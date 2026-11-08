"""A rejected CRUD write must not leak into readers or a later successful save."""

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collections.models import Collection
from src.collections.storage import CollectionStorage
from src.pages.models import Page
from src.pages.storage import PageStorage
from src.schedules.models import ScheduleEntry
from src.schedules.storage import ScheduleStorage


def page(key, value):
    return Page(id=key, name=value, type="template", template=["HELLO"])


def collection(key, value):
    return Collection(id=f"collection:{key}", name=value, page_ids=["page-one"])


def schedule(key, value):
    return ScheduleEntry(id=key, page_id=value, start_time="09:00")


STORES = (
    ("pages", PageStorage, page, "name"),
    ("collections", CollectionStorage, collection, "name"),
    ("schedules", ScheduleStorage, schedule, "page_id"),
)


class TestStorageFailedMutations(unittest.TestCase):
    def check_failed_write(self, operation):
        for label, storage_type, make_record, field in STORES:
            with self.subTest(store=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{label}.json"
                store = storage_type(str(path))
                original = make_record("original", "Original")
                store.create(original)
                original_bytes = path.read_bytes()
                observed = []

                def reject_commit(*args, observed=observed, field=field, store=store, **kwargs):
                    observed.append({item.id: getattr(item, field) for item in store.list_all()})
                    raise OSError(errno.ENOSPC, "synthetic disk full")

                with patch("src.atomic_io.os.replace", side_effect=reject_commit):
                    with self.assertRaises(OSError):
                        if operation == "create":
                            store.create(make_record("rejected", "Rejected"))
                        elif operation == "update":
                            store.update(original.id, {field: "Rejected"})
                        else:
                            store.delete(original.id)
                self.assertEqual(path.read_bytes(), original_bytes)

                # An unrelated accepted write must not make the failed request
                # durable later, even without restarting the running service.
                accepted = make_record("accepted", "Accepted")
                store.create(accepted)
                reloaded = storage_type(str(path))
                self.assertEqual(
                    {item.id: getattr(item, field) for item in reloaded.list_all()},
                    {original.id: "Original", accepted.id: "Accepted"},
                )
                self.assertEqual(observed, [{original.id: "Original"}])

    def test_failed_create_is_not_published_or_saved_later(self):
        self.check_failed_write("create")

    def test_failed_update_is_not_published_or_saved_later(self):
        self.check_failed_write("update")

    def test_failed_delete_is_not_published_or_saved_later(self):
        self.check_failed_write("delete")
