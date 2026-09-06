"""
Cost tracking module for cloud LLM usage.
Tracks token usage and estimated costs per session/request.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from core.config import config
from core.logger import setup_logger

logger = setup_logger("CostTracker")

# Pricing per 1M tokens (input, output) in USD
# Updated as of 2025 - these are estimates
MODEL_PRICING: Dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4-vision": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    # Anthropic
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    # Google
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
    # NVIDIA
    "nemotron-3-ultra": (0.00, 0.00),  # Free via NVIDIA API
    # Local models (free)
    "llava": (0.00, 0.00),
    "llava-next": (0.00, 0.00),
    "qwen2.5vl": (0.00, 0.00),
    "qwen2-vl": (0.00, 0.00),
    "pixtral": (0.00, 0.00),
}


@dataclass
class UsageRecord:
    """Single LLM request usage record."""
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: float = field(default_factory=time.time)
    operation: str = "unknown"  # e.g., "vision_verify", "vision_ask", "plan", "worker"


@dataclass
class SessionCosts:
    """Aggregated costs for a session."""
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    records: list[UsageRecord] = field(default_factory=list)

    def add_record(self, record: UsageRecord) -> None:
        self.records.append(record)
        self.total_cost_usd += record.cost_usd
        self.total_input_tokens += record.input_tokens
        self.total_output_tokens += record.output_tokens

    def get_summary(self) -> dict:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "request_count": len(self.records),
            "by_model": self._by_model(),
            "by_operation": self._by_operation(),
        }

    def _by_model(self) -> dict:
        result = {}
        for r in self.records:
            if r.model not in result:
                result[r.model] = {"cost": 0.0, "input": 0, "output": 0, "count": 0}
            result[r.model]["cost"] += r.cost_usd
            result[r.model]["input"] += r.input_tokens
            result[r.model]["output"] += r.output_tokens
            result[r.model]["count"] += 1
        return {k: {**v, "cost": round(v["cost"], 6)} for k, v in result.items()}

    def _by_operation(self) -> dict:
        result = {}
        for r in self.records:
            if r.operation not in result:
                result[r.operation] = {"cost": 0.0, "count": 0}
            result[r.operation]["cost"] += r.cost_usd
            result[r.operation]["count"] += 1
        return {k: {**v, "cost": round(v["cost"], 6)} for k, v in result.items()}


class CostTracker:
    """
    Tracks LLM token usage and costs across the session.
    Enforces per-request and per-session budget limits.
    """
    _instance: Optional["CostTracker"] = None

    def __new__(cls) -> "CostTracker":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.session = SessionCosts()
        self._initialized = True
        # Load persisted session costs if any
        self._load_session()

    def _get_pricing(self, model: str) -> tuple[float, float]:
        """Get pricing for a model, with fuzzy matching."""
        model_lower = model.lower()
        for key, pricing in MODEL_PRICING.items():
            if key in model_lower or model_lower in key:
                return pricing
        # Default fallback
        return (0.00, 0.00)

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a request."""
        input_price, output_price = self._get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    def can_afford_request(self, model: str, estimated_input_tokens: int, estimated_output_tokens: int) -> tuple[bool, str]:
        """Check if a request fits within budget limits."""
        if not config.cloud_vision_enabled:
            return True, ""

        estimated_cost = self.estimate_cost(model, estimated_input_tokens, estimated_output_tokens)

        # Check per-request limit
        if estimated_cost > config.max_vision_cost_per_request_usd:
            return False, f"Estimated cost ${estimated_cost:.4f} exceeds per-request limit ${config.max_vision_cost_per_request_usd:.4f}"

        # Check per-session limit
        if self.session.total_cost_usd + estimated_cost > config.max_vision_cost_per_session_usd:
            return False, f"Session cost ${self.session.total_cost_usd:.4f} + ${estimated_cost:.4f} would exceed session limit ${config.max_vision_cost_per_session_usd:.4f}"

        return True, ""

    def record_usage(self, model: str, input_tokens: int, output_tokens: int, operation: str = "unknown") -> UsageRecord:
        """Record actual usage after a request."""
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        record = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            operation=operation,
        )
        self.session.add_record(record)
        self._save_session()
        logger.info(f"Cost: ${cost:.6f} | Session total: ${self.session.total_cost_usd:.4f} | {operation} via {model}")
        return record

    def get_session_summary(self) -> dict:
        """Get current session cost summary."""
        return self.session.get_summary()

    def reset_session(self) -> None:
        """Reset session costs (e.g., on new user session)."""
        self.session = SessionCosts()
        self._save_session()

    def _session_file(self) -> str:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, ".session_costs.json")

    def _save_session(self) -> None:
        """Persist session costs to disk."""
        try:
            data = {
                "total_cost_usd": self.session.total_cost_usd,
                "total_input_tokens": self.session.total_input_tokens,
                "total_output_tokens": self.session.total_output_tokens,
                "records": [
                    {
                        "model": r.model,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "cost_usd": r.cost_usd,
                        "timestamp": r.timestamp,
                        "operation": r.operation,
                    }
                    for r in self.session.records
                ],
            }
            with open(self._session_file(), "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"Could not save session costs: {e}")

    def _load_session(self) -> None:
        """Load session costs from disk."""
        try:
            if os.path.exists(self._session_file()):
                with open(self._session_file(), "r") as f:
                    data = json.load(f)
                self.session.total_cost_usd = data.get("total_cost_usd", 0.0)
                self.session.total_input_tokens = data.get("total_input_tokens", 0)
                self.session.total_output_tokens = data.get("total_output_tokens", 0)
                for r in data.get("records", []):
                    self.session.records.append(UsageRecord(**r))
        except Exception as e:
            logger.debug(f"Could not load session costs: {e}")


def get_cost_tracker() -> CostTracker:
    """Get the singleton CostTracker instance."""
    return CostTracker()