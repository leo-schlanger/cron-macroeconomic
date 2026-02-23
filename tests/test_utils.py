"""
Testes para o módulo utils.
"""
import pytest
import time
import sys
from pathlib import Path

# Adicionar diretório pai ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    retry,
    retry_call,
    RetryError,
    RateLimiter,
    Timer,
    setup_logging
)


class TestRetryDecorator:
    """Testes para o decorator retry."""

    def test_success_on_first_try(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "success"

        result = always_succeeds()
        assert result == "success"
        assert call_count == 1

    def test_success_after_failures(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"

        result = fails_twice()
        assert result == "success"
        assert call_count == 3

    def test_raise_after_max_attempts(self):
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(RetryError) as exc_info:
            always_fails()

        assert call_count == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    def test_only_catch_specified_exceptions(self):
        @retry(max_attempts=3, delay=0.01, exceptions=(ValueError,))
        def raises_type_error():
            raise TypeError("Wrong type")

        with pytest.raises(TypeError):
            raises_type_error()

    def test_exponential_backoff(self):
        call_times = []

        @retry(max_attempts=3, delay=0.1, backoff=2.0)
        def track_timing():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Retry")
            return "done"

        track_timing()

        # Verificar que delays aumentam
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        assert delay1 >= 0.09  # ~0.1s
        assert delay2 >= 0.18  # ~0.2s (backoff 2x)

    def test_on_retry_callback(self):
        retry_info = []

        def on_retry(exc, attempt):
            retry_info.append((str(exc), attempt))

        @retry(max_attempts=3, delay=0.01, on_retry=on_retry)
        def fails_twice():
            if len(retry_info) < 2:
                raise ValueError(f"Attempt {len(retry_info) + 1}")
            return "success"

        fails_twice()

        assert len(retry_info) == 2
        assert retry_info[0][1] == 1
        assert retry_info[1][1] == 2


class TestRetryCall:
    """Testes para a função retry_call."""

    def test_success(self):
        def add(a, b):
            return a + b

        result = retry_call(add, args=(2, 3))
        assert result == 5

    def test_with_kwargs(self):
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        result = retry_call(greet, args=("World",), kwargs={"greeting": "Hi"})
        assert result == "Hi, World!"

    def test_retry_on_failure(self):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("First call fails")
            return "success"

        result = retry_call(flaky, max_attempts=3, delay=0.01)
        assert result == "success"
        assert call_count == 2


class TestRateLimiter:
    """Testes para a classe RateLimiter."""

    def test_burst_allowed(self):
        limiter = RateLimiter(calls_per_second=10, burst=5)

        start = time.time()
        for _ in range(5):
            limiter.wait()
        elapsed = time.time() - start

        # Burst de 5 deve ser quase instantâneo
        assert elapsed < 0.5

    def test_rate_limiting(self):
        limiter = RateLimiter(calls_per_second=10, burst=1)

        times = []
        for _ in range(3):
            limiter.wait()
            times.append(time.time())

        # Intervalo deve ser ~0.1s entre chamadas
        interval1 = times[1] - times[0]
        interval2 = times[2] - times[1]

        assert interval1 >= 0.08  # ~100ms
        assert interval2 >= 0.08

    def test_context_manager(self):
        limiter = RateLimiter(calls_per_second=10)

        with limiter:
            pass  # Deve funcionar sem erros


class TestTimer:
    """Testes para a classe Timer."""

    def test_measure_duration(self):
        with Timer("test") as t:
            time.sleep(0.1)

        assert t.duration >= 0.1
        assert t.duration < 0.2

    def test_elapsed_ms(self):
        with Timer("test") as t:
            time.sleep(0.05)

        assert t.elapsed_ms >= 50
        assert t.elapsed_ms < 100

    def test_elapsed_during_execution(self):
        with Timer("test") as t:
            time.sleep(0.05)
            mid_elapsed = t.elapsed_ms
            time.sleep(0.05)

        assert mid_elapsed >= 50
        assert t.elapsed_ms >= 100


class TestSetupLogging:
    """Testes para a função setup_logging."""

    def test_create_logger(self):
        logger = setup_logging("test_logger")
        assert logger is not None
        assert logger.name == "test_logger"

    def test_logger_has_handlers(self):
        logger = setup_logging("test_handlers")
        assert len(logger.handlers) > 0

    def test_reuse_existing_logger(self):
        logger1 = setup_logging("reuse_test")
        handler_count = len(logger1.handlers)

        logger2 = setup_logging("reuse_test")

        # Não deve adicionar handlers duplicados
        assert len(logger2.handlers) == handler_count


class TestRetryErrorException:
    """Testes para a exceção RetryError."""

    def test_message(self):
        original = ValueError("Original error")
        error = RetryError("Failed after 3 attempts", original)

        assert "Failed after 3 attempts" in str(error)

    def test_last_exception(self):
        original = ValueError("Original error")
        error = RetryError("Failed", original)

        assert error.last_exception is original
        assert isinstance(error.last_exception, ValueError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
