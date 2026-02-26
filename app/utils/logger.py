"""
로깅 유틸리티 모듈
- INFO 이상: 터미널 출력 (ANSI 컬러)
- DEBUG 이상: 파일 기록 (logs/ophtimus.log, 로테이션)
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 프로젝트 루트 기준 logs/ 디렉터리
_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "ophtimus.log"

# ANSI 컬러 코드
_COLORS = {
    "DEBUG":    "\033[90m",   # 회색
    "INFO":     "\033[97m",   # 밝은 흰색
    "WARNING":  "\033[93m",   # 노란색
    "ERROR":    "\033[91m",   # 빨간색
    "CRITICAL": "\033[95m",   # 마젠타
    "RESET":    "\033[0m",
}


class _ColorFormatter(logging.Formatter):
    """터미널 출력에 ANSI 컬러를 적용하는 Formatter."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _COLORS["RESET"])
        reset = _COLORS["RESET"]
        # levelname 컬러 적용 (포맷 후 원본 복구)
        original_levelname = record.levelname
        record.levelname = f"{color}{record.levelname:<8}{reset}"
        formatted = super().format(record)
        record.levelname = original_levelname
        return formatted


def get_logger(name: str) -> logging.Logger:
    """지정한 이름으로 logger를 반환한다.

    동일 이름으로 재호출 시 기존 logger를 재사용하여 핸들러 중복을 방지한다.

    Args:
        name: 보통 __name__ 을 전달 (예: app.node.consultation_agent)

    Returns:
        설정이 완료된 logging.Logger 인스턴스
    """
    logger = logging.getLogger(name)

    # 핸들러가 이미 등록된 경우 재사용 (중복 방지)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # 루트 logger로 전파 차단

    # ── 터미널 핸들러 (INFO 이상, 컬러) ─────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        _ColorFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # ── 파일 핸들러 (DEBUG 이상, 로테이션) ──────────────────────────────────
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger
