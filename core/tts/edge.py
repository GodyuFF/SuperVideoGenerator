"""Edge TTS（Azure v1 兼容路径）合成。"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import queue
import threading
import time

import edge_tts
from edge_tts import SubMaker

from core.tts.silent import ensure_file_path_exists
from core.tts.text import convert_rate_to_percent
from core.tts.voices import parse_voice_name

logger = logging.getLogger("core.tts.edge")

_DEFAULT_EDGE_TTS_TIMEOUT_SECONDS = 30.0


def create_edge_tts_communicate(
    text: str, voice_name: str, rate_str: str
) -> edge_tts.Communicate:
    communicate_kwargs = {"rate": rate_str}
    communicate_signature = inspect.signature(edge_tts.Communicate)
    if "boundary" in communicate_signature.parameters:
        communicate_kwargs["boundary"] = "WordBoundary"
    return edge_tts.Communicate(text, voice_name, **communicate_kwargs)


def _stream_edge_tts_sync_with_timeout(
    communicate, on_chunk, timeout_seconds: float
) -> None:
    stream_queue: queue.Queue = queue.Queue()
    done_marker = object()

    def _produce_chunks():
        try:
            for chunk in communicate.stream_sync():
                stream_queue.put(("chunk", chunk))
            stream_queue.put(("done", done_marker))
        except Exception as e:
            stream_queue.put(("error", e))

    thread = threading.Thread(target=_produce_chunks, daemon=True)
    thread.start()

    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise TimeoutError(
                f"edge_tts stream timed out after {timeout_seconds:g}s"
            )
        try:
            item_type, payload = stream_queue.get(timeout=min(0.5, remaining_seconds))
        except queue.Empty:
            continue
        if item_type == "chunk":
            on_chunk(payload)
        elif item_type == "error":
            raise payload
        elif item_type == "done":
            return


def stream_edge_tts_chunks(
    communicate,
    on_chunk,
    timeout_seconds: float | None = None,
) -> None:
    if hasattr(communicate, "stream_sync"):
        if timeout_seconds:
            _stream_edge_tts_sync_with_timeout(
                communicate, on_chunk, timeout_seconds
            )
            return
        for chunk in communicate.stream_sync():
            on_chunk(chunk)
        return

    if not hasattr(communicate, "stream"):
        raise AttributeError("edge_tts communicate object has no stream method")

    async def _consume_async_stream():
        async for chunk in communicate.stream():
            on_chunk(chunk)

    loop = asyncio.new_event_loop()
    try:
        if timeout_seconds:
            loop.run_until_complete(
                asyncio.wait_for(_consume_async_stream(), timeout=timeout_seconds)
            )
        else:
            loop.run_until_complete(_consume_async_stream())
    finally:
        loop.close()


def synthesize_edge_tts(
    text: str,
    voice_name: str,
    voice_rate: float,
    voice_file: str,
    *,
    timeout_seconds: float | None = None,
) -> SubMaker | None:
    voice_name = parse_voice_name(voice_name)
    text = text.strip()
    rate_str = convert_rate_to_percent(voice_rate)
    timeout = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None

    for i in range(3):
        try:
            logger.info("edge tts start voice=%s try=%s", voice_name, i + 1)
            ensure_file_path_exists(voice_file)
            communicate = create_edge_tts_communicate(text, voice_name, rate_str)
            sub_maker = edge_tts.SubMaker()

            with open(voice_file, "wb") as file:
                def _handle_chunk(chunk):
                    chunk_type = chunk["type"]
                    if chunk_type == "audio":
                        file.write(chunk["data"])
                    elif chunk_type in ("WordBoundary", "SentenceBoundary"):
                        sub_maker.feed(chunk)

                stream_edge_tts_chunks(
                    communicate, _handle_chunk, timeout_seconds=timeout
                )

            if not sub_maker.get_srt():
                logger.warning("edge tts sub_maker.get_srt() empty")
                continue
            logger.info("edge tts completed file=%s", voice_file)
            return sub_maker
        except Exception as e:
            logger.error("edge tts failed: %s", e)
            if os.path.exists(voice_file) and os.path.getsize(voice_file) == 0:
                try:
                    os.remove(voice_file)
                except OSError:
                    pass
    return None
