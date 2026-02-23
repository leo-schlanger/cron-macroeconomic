"""
Módulo de utilidades: logging, retry, rate limiting.
"""
import logging
import time
import functools
from typing import Callable, TypeVar, Optional
from datetime import datetime

# Type var para funções genéricas
T = TypeVar('T')


# ============================================================
# LOGGING CONFIGURAÇÃO
# ============================================================

def setup_logging(
    name: str = "macronews",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Configura logging estruturado.

    Args:
        name: Nome do logger
        level: Nível de log (INFO, DEBUG, etc.)
        log_file: Arquivo de log opcional

    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)

    # Evitar duplicação de handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Formato estruturado
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (opcional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Logger padrão
logger = setup_logging()


# ============================================================
# RETRY COM EXPONENTIAL BACKOFF
# ============================================================

class RetryError(Exception):
    """Exceção lançada quando todas as tentativas falham."""
    def __init__(self, message: str, last_exception: Exception):
        super().__init__(message)
        self.last_exception = last_exception


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator para retry com exponential backoff.

    Args:
        max_attempts: Número máximo de tentativas
        delay: Delay inicial em segundos
        backoff: Fator de multiplicação do delay
        exceptions: Tupla de exceções para capturar
        on_retry: Callback chamado em cada retry (exception, attempt)

    Example:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        def fetch_data():
            return requests.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        break

                    if on_retry:
                        on_retry(e, attempt)
                    else:
                        logger.warning(
                            f"Tentativa {attempt}/{max_attempts} falhou: {e}. "
                            f"Retry em {current_delay:.1f}s..."
                        )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise RetryError(
                f"Falhou após {max_attempts} tentativas",
                last_exception
            )

        return wrapper
    return decorator


def retry_call(
    func: Callable[..., T],
    args: tuple = (),
    kwargs: dict = None,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> T:
    """
    Executa função com retry (versão não-decorator).

    Args:
        func: Função a executar
        args: Argumentos posicionais
        kwargs: Argumentos nomeados
        max_attempts: Número máximo de tentativas
        delay: Delay inicial em segundos
        backoff: Fator de multiplicação do delay
        exceptions: Tupla de exceções para capturar

    Returns:
        Resultado da função

    Example:
        result = retry_call(requests.get, args=(url,), max_attempts=3)
    """
    kwargs = kwargs or {}
    current_delay = delay
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt == max_attempts:
                break

            logger.warning(
                f"Tentativa {attempt}/{max_attempts} falhou: {e}. "
                f"Retry em {current_delay:.1f}s..."
            )

            time.sleep(current_delay)
            current_delay *= backoff

    raise RetryError(
        f"Falhou após {max_attempts} tentativas",
        last_exception
    )


# ============================================================
# RATE LIMITING
# ============================================================

class RateLimiter:
    """
    Rate limiter simples baseado em token bucket.

    Example:
        limiter = RateLimiter(calls_per_second=2)
        for url in urls:
            limiter.wait()
            fetch(url)
    """

    def __init__(self, calls_per_second: float = 1.0, burst: int = 1):
        """
        Args:
            calls_per_second: Taxa máxima de chamadas por segundo
            burst: Número de chamadas permitidas em rajada
        """
        self.min_interval = 1.0 / calls_per_second
        self.burst = burst
        self.tokens = burst
        self.last_time = time.time()

    def wait(self):
        """Aguarda se necessário para respeitar o rate limit."""
        now = time.time()
        elapsed = now - self.last_time

        # Repor tokens baseado no tempo
        self.tokens = min(self.burst, self.tokens + elapsed / self.min_interval)

        if self.tokens < 1:
            # Precisa aguardar
            wait_time = (1 - self.tokens) * self.min_interval
            time.sleep(wait_time)
            self.tokens = 0
        else:
            self.tokens -= 1

        self.last_time = time.time()

    def __enter__(self):
        self.wait()
        return self

    def __exit__(self, *args):
        pass


# Rate limiter global para requests (2 req/sec por padrão)
request_limiter = RateLimiter(calls_per_second=2.0, burst=5)


# ============================================================
# UTILIDADES DE TEMPO
# ============================================================

class Timer:
    """Context manager para medir tempo de execução."""

    def __init__(self, name: str = "operação"):
        self.name = name
        self.start = None
        self.end = None
        self.duration = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.duration = self.end - self.start
        logger.debug(f"{self.name} levou {self.duration:.2f}s")

    @property
    def elapsed_ms(self) -> int:
        """Retorna duração em milissegundos."""
        if self.duration is not None:
            return int(self.duration * 1000)
        return int((time.time() - self.start) * 1000)


# ============================================================
# TESTES
# ============================================================

if __name__ == "__main__":
    # Teste de logging
    logger.info("Teste de logging INFO")
    logger.warning("Teste de logging WARNING")
    logger.error("Teste de logging ERROR")

    # Teste de retry
    @retry(max_attempts=3, delay=0.5, exceptions=(ValueError,))
    def flaky_function(fail_times: int):
        flaky_function.calls = getattr(flaky_function, 'calls', 0) + 1
        if flaky_function.calls <= fail_times:
            raise ValueError(f"Falha {flaky_function.calls}")
        return "sucesso"

    print("\n--- Teste retry (deve falhar 2x e suceder na 3a) ---")
    result = flaky_function(2)
    print(f"Resultado: {result}")

    # Teste de rate limiter
    print("\n--- Teste rate limiter (2 req/s) ---")
    limiter = RateLimiter(calls_per_second=2)
    for i in range(5):
        start = time.time()
        limiter.wait()
        print(f"Request {i+1} em t={time.time() - start:.2f}s")

    # Teste de Timer
    print("\n--- Teste Timer ---")
    with Timer("operação de teste") as t:
        time.sleep(0.1)
    print(f"Duração: {t.elapsed_ms}ms")
