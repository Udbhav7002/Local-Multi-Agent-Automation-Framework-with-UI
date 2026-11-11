

class TestConfig:
    def test_os_context_returns_string(self):
        from core.config import config
        ctx = config.os_context
        assert isinstance(ctx, str)
        assert len(ctx) > 20

    def test_default_models_set(self):
        from core.config import config
        assert config.manager_model
        assert config.worker_model
        assert config.vision_model

    def test_action_timeouts_populated(self):
        from core.config import config
        assert "run_command" in config.action_timeouts
        assert "goto" in config.action_timeouts
        assert config.action_timeouts["run_command"] > 0

    def test_num_ctx_has_sensible_default(self):
        from core.config import config
        assert 1024 <= config.num_ctx <= 65536
