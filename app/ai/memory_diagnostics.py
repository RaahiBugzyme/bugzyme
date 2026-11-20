"""Lightweight memory and process diagnostics for Bugzyme.

Uses standard library resource module to track RSS memory in MB.
No external dependencies (no psutil needed), zero memory overhead.
Never logs private conversation messages, user memories, or sensitive data.
"""

import logging
import os
import resource
import sys
from typing import Optional

logger = logging.getLogger("bugzyme.diagnostics")


def get_process_rss_mb() -> float:
    """Return current process Resident Set Size (RSS) in megabytes.

    Works accurately across macOS (where ru_maxrss is in bytes)
    and Linux (where ru_maxrss is in kilobytes).
    """
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(usage / (1024 * 1024), 2)
        # Linux reports in kilobytes
        return round(usage / 1024, 2)
    except Exception:
        return 0.0


def log_memory_snapshot(stage: str, extra: Optional[str] = None) -> float:
    """Log a clean memory snapshot with the given stage name.

    Returns the RSS in MB.
    """
    rss = get_process_rss_mb()
    if extra:
        logger.info("[Memory] %s | RSS: %.2f MB | %s", stage, rss, extra)
    else:
        logger.info("[Memory] %s | RSS: %.2f MB", stage, rss)
    return rss
