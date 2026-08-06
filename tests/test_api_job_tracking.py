import os
import sqlite3
import uuid
import pytest
from api import JobStore

def test_job_store_lifecycle(tmp_path):
    db_path = str(tmp_path / "test_jobs.db")
    store = JobStore(db_path=db_path)

    # Test not found
    assert store.get_job("fake-id") is None

    # Test create
    job_id = str(uuid.uuid4())
    store.create_job(job_id)

    job = store.get_job(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == "QUEUED"
    assert job["result"] is None
    assert job["steps_executed"] is None

    # Test update status
    store.update_job(job_id, "RUNNING")
    job = store.get_job(job_id)
    assert job["status"] == "RUNNING"

    # Test update with result and steps
    store.update_job(job_id, "COMPLETED", result="Success!", steps_executed=["step 1", "step 2"])
    job = store.get_job(job_id)
    assert job["status"] == "COMPLETED"
    assert job["result"] == "Success!"
    assert '["step 1", "step 2"]' in job["steps_executed"]
