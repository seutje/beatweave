import asyncio
from unittest.mock import Mock

from beatweave.asyncio_errors import (
    install_disconnect_exception_handler,
    is_benign_proactor_disconnect,
)


def proactor_reset() -> ConnectionResetError:
    return ConnectionResetError(10054, "An existing connection was forcibly closed")


def test_recognizes_only_connection_reset_during_proactor_cleanup() -> None:
    assert is_benign_proactor_disconnect(
        {
            "message": "Exception in callback",
            "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
            "exception": proactor_reset(),
        }
    )
    assert not is_benign_proactor_disconnect(
        {"handle": "<Handle another_callback()>", "exception": proactor_reset()}
    )
    assert not is_benign_proactor_disconnect(
        {
            "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
            "exception": RuntimeError("unexpected"),
        }
    )


def test_handler_suppresses_benign_reset_and_delegates_other_errors() -> None:
    loop = Mock(spec=asyncio.AbstractEventLoop)
    previous = Mock()
    loop.get_exception_handler.return_value = previous

    assert install_disconnect_exception_handler(loop) is previous
    handler = loop.set_exception_handler.call_args.args[0]
    benign = {
        "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
        "exception": proactor_reset(),
    }
    unexpected = {"exception": RuntimeError("unexpected")}

    handler(loop, benign)
    previous.assert_not_called()
    handler(loop, unexpected)
    previous.assert_called_once_with(loop, unexpected)


def test_handler_uses_asyncio_default_without_a_previous_handler() -> None:
    loop = Mock(spec=asyncio.AbstractEventLoop)
    loop.get_exception_handler.return_value = None
    install_disconnect_exception_handler(loop)
    handler = loop.set_exception_handler.call_args.args[0]
    context = {"exception": RuntimeError("unexpected")}

    handler(loop, context)

    loop.default_exception_handler.assert_called_once_with(context)
