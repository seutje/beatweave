import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

ExceptionHandler = Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None]


def is_benign_proactor_disconnect(context: Mapping[str, Any]) -> bool:
    """Return whether a browser closed a Windows Proactor media connection.

    Chromium commonly closes an HTTP range request once it has enough video
    metadata.  CPython's Windows Proactor loop can report that normal client
    disconnect while its transport is already being torn down.
    """
    exception = context.get("exception")
    if not isinstance(exception, ConnectionResetError):
        return False
    error_number = getattr(exception, "winerror", None)
    if error_number is None and exception.args:
        error_number = exception.args[0]
    if error_number != 10054:
        return False
    callback = str(context.get("handle", ""))
    message = str(context.get("message", ""))
    return "_call_connection_lost" in callback or "_call_connection_lost" in message


def install_disconnect_exception_handler(
    loop: asyncio.AbstractEventLoop,
) -> ExceptionHandler | None:
    """Suppress only the known benign Proactor disconnect and delegate the rest."""
    previous = loop.get_exception_handler()

    def handle_exception(current_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if is_benign_proactor_disconnect(context):
            logger.debug("Media client disconnected during transport cleanup")
            return
        if previous is not None:
            previous(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)
    return previous
