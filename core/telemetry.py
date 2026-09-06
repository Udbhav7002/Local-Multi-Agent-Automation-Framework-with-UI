"""
OpenTelemetry integration for tracing agent latency and execution paths.
"""
import functools
import time
from typing import Callable, Any

from opentelemetry import trace
from opentelemetry.trace import format_trace_id
from core.logger import set_task_id
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Initialize OpenTelemetry
provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("agent-automation")

def trace_latency(name: str) -> Callable:
    """
    Decorator to measure and trace the latency of any async agent function.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            with tracer.start_as_current_span(name) as span:
                trace_id = format_trace_id(span.get_span_context().trace_id)
                set_task_id(trace_id)
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error.message", str(e))
                    raise
                finally:
                    duration = time.time() - start_time
                    span.set_attribute("duration_s", duration)
        return wrapper
    return decorator
