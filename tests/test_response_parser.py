import pytest

from core.response_parser import ResponseParser


class TestCleanAndExtractJson:
    def test_clean_json_array(self):
        raw = '[{"task": "open app", "parallel": false}]'
        result = ResponseParser.clean_and_extract_json(raw, shape="array")
        assert '"task"' in result

    def test_strip_markdown_fences(self):
        raw = '```json\n[{"task": "test"}]\n```'
        result = ResponseParser.clean_and_extract_json(raw, shape="array")
        assert '"task"' in result

    def test_strip_think_blocks(self):
        raw = '<think>reasoning here</think>[{"task": "test"}]'
        result = ResponseParser.clean_and_extract_json(raw, shape="array")
        assert '"task"' in result

    def test_trailing_comma_removal(self):
        raw = '[{"task": "test",}]'
        result = ResponseParser.clean_and_extract_json(raw, shape="array")
        assert '"task"' in result

    def test_embedded_prose(self):
        raw = 'Here is my plan:\n[{"task": "step 1"}]\nHope this helps!'
        result = ResponseParser.clean_and_extract_json(raw, shape="array")
        assert '"task"' in result

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            ResponseParser.clean_and_extract_json("not json at all", shape="array")

    def test_object_shape(self):
        raw = '{"approved": true, "feedback": "looks good"}'
        result = ResponseParser.clean_and_extract_json(raw, shape="object")
        assert '"approved"' in result


class TestParseWorkerOutput:
    def test_list_input(self):
        raw = '[{"action": "run_command", "target": "ls", "method": "cli"}]'
        result = ResponseParser.parse_worker_output(raw)
        assert len(result) == 1
        assert result[0]["action"] == "run_command"

    def test_dict_input_wrapped(self):
        raw = '{"action": "click", "target": "button", "method": "gui"}'
        result = ResponseParser.parse_worker_output(raw)
        assert len(result) == 1

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            ResponseParser.parse_worker_output('"just a string"')
