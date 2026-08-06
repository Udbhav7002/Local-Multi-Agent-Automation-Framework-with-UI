"""
Unit tests for SkillLibrary in-memory caching and semantic deduplication.
"""
import os
import json
import builtins
import pytest
from memory.skill_library import SkillLibrary


def test_in_memory_startup_caching(tmp_path):
    skills_dir = str(tmp_path)
    lib1 = SkillLibrary(skills_dir=skills_dir)
    lib1.save_skill("Open Chrome browser", '{"steps": ["launch chrome"]}')

    # Second instance pointing to the same directory should populate cache on startup
    lib2 = SkillLibrary(skills_dir=skills_dir)
    assert len(lib2._cache) == 1
    skill_id = list(lib2._cache.keys())[0]
    assert lib2._cache[skill_id]["trigger_phrases"] == ["open chrome browser"]


def test_o1_lookup_performance_no_disk_read(tmp_path, monkeypatch):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)
    plan_data = '{"steps": ["open browser", "navigate example.com"]}'
    task_desc = "open browser and navigate to example.com"
    lib.save_skill(task_desc, plan_data)

    # Disallow open() and os.listdir to verify O(1) in-memory lookups
    original_open = builtins.open

    def mock_open(*args, **kwargs):
        # Allow opening files outside skills_dir or python internal files if any
        file_arg = str(args[0]) if args else ""
        if skills_dir in file_arg:
            raise AssertionError("Disk I/O open() called during in-memory get_skill_plan lookup!")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", mock_open)
    monkeypatch.setattr(os, "listdir", lambda d: pytest.fail("os.listdir called during in-memory lookup!"))

    retrieved = lib.get_skill_plan(task_desc)
    assert retrieved == plan_data


def test_semantic_deduplication(tmp_path):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)

    task1 = "open google chrome browser"
    task2 = "open google chrome"
    plan1 = '{"steps": ["open chrome"]}'
    plan2 = '{"steps": ["open chrome", "maximize window"]}'

    lib.save_skill(task1, plan1)
    assert len(lib._cache) == 1

    # Saving semantically similar task should update existing skill, not duplicate
    lib.save_skill(task2, plan2)
    assert len(lib._cache) == 1

    # Verify disk files
    json_files = [f for f in os.listdir(skills_dir) if f.endswith(".json")]
    assert len(json_files) == 1

    skill_data = list(lib._cache.values())[0]
    assert skill_data["success_count"] == 2
    assert "open google chrome browser" in skill_data["trigger_phrases"]
    assert "open google chrome" in skill_data["trigger_phrases"]
    assert skill_data["plan_json"] == plan2


def test_fuzzy_retrieval(tmp_path):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)

    task_original = "search for python documentation on google search"
    plan = '{"steps": ["go to google.com", "type python docs"]}'
    lib.save_skill(task_original, plan)

    # Retrieval with slightly different phrasing
    task_query = "search python documentation on google"
    retrieved = lib.get_skill_plan(task_query)
    assert retrieved == plan


def test_success_rate_filtering_and_failure(tmp_path):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)

    task = "click login button"
    plan = '{"steps": ["click login"]}'
    lib.save_skill(task, plan)

    assert lib.get_skill_plan(task) == plan

    # Mark as failed twice (1 success, 2 fails -> 33% success rate)
    lib.mark_failure(task)
    lib.mark_failure(task)

    # Success rate < 50%, should return None
    assert lib.get_skill_plan(task) is None


def test_error_handling_and_corrupt_files(tmp_path):
    skills_dir = str(tmp_path)

    # Create a corrupted JSON file
    corrupt_file = os.path.join(skills_dir, "corrupt_skill.json")
    os.makedirs(skills_dir, exist_ok=True)
    with open(corrupt_file, "w", encoding="utf-8") as f:
        f.write("{ invalid json content ...")

    # Create a valid JSON file
    valid_skill = {
        "skill_id": "valid_skill_123",
        "trigger_phrases": ["valid test task"],
        "plan_json": '{"steps": ["valid"]}',
        "success_count": 1,
        "fail_count": 0
    }
    with open(os.path.join(skills_dir, "valid_skill_123.json"), "w", encoding="utf-8") as f:
        json.dump(valid_skill, f)

    # Startup should log error for corrupt file and load valid file
    lib = SkillLibrary(skills_dir=skills_dir)
    assert len(lib._cache) == 1
    assert "valid_skill_123" in lib._cache
    assert lib.get_skill_plan("valid test task") == '{"steps": ["valid"]}'


def test_empty_or_missing_dir(tmp_path):
    missing_dir = os.path.join(str(tmp_path), "non_existent_subdir")
    lib = SkillLibrary(skills_dir=missing_dir)

    assert lib.get_skill_plan("non existent skill") is None

    # Saving should automatically create missing dir and persist skill
    lib.save_skill("test action", '{"steps": ["act"]}')
    assert os.path.exists(missing_dir)
    assert len(os.listdir(missing_dir)) == 1


def test_empty_and_whitespace_task_description_validation(tmp_path):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)
    
    # Pre-populate a skill
    lib.save_skill("open web page", '{"steps": ["open browser"]}')
    assert len(lib._cache) == 1

    # Empty and whitespace lookups should return None without error
    assert lib.get_skill_plan("") is None
    assert lib.get_skill_plan("   ") is None
    assert lib.get_skill_plan("\t\n") is None
    assert lib.get_skill_plan(None) is None

    # Empty and whitespace save_skill should do nothing without error
    lib.save_skill("", '{"steps": ["nothing"]}')
    lib.save_skill("   ", '{"steps": ["nothing"]}')
    lib.save_skill(None, '{"steps": ["nothing"]}')
    assert len(lib._cache) == 1

    # Empty and whitespace mark_failure should do nothing without error
    lib.mark_failure("")
    lib.mark_failure("   ")
    lib.mark_failure(None)
    assert lib._cache[list(lib._cache.keys())[0]]["fail_count"] == 0


def test_no_substring_false_positive(tmp_path):
    skills_dir = str(tmp_path)
    lib = SkillLibrary(skills_dir=skills_dir)
    
    # Save a short 1-step skill
    lib.save_skill("open safari", '{"steps": ["open safari"]}')
    
    # Looking up a much longer multi-step task containing the substring should NOT match
    assert lib.get_skill_plan("open safari and search black mytrh wuokung") is None


