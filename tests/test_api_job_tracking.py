import json

import pytest

from api import JobStore


@pytest.mark.asyncio
async def test_job_store_lifecycle(tmp_path):
    db_path = str(tmp_path / "test_jobs.db")
    store = JobStore(db_path=db_path)
    await store.connect()

    # Test not found
    assert await store.get_job("fake-id") is None

    # Test create
    job_id = "job-123"
    await store.create_job(job_id, "Run this prompt")

    job = await store.get_job(job_id)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == "QUEUED"

    # Test update status
    await store.update_job(job_id, "RUNNING")
    job = await store.get_job(job_id)
    assert job is not None
    assert job["status"] == "RUNNING"

    # Test update with result and steps
    await store.update_job(job_id, "COMPLETED", result="Success!", steps_executed=[{"action": "test"}])
    job = await store.get_job(job_id)
    assert job is not None
    assert job["status"] == "COMPLETED"
    assert job["result"] == "Success!"
    assert json.loads(job["steps_executed"]) == [{"action": "test"}]

    await store.close()
