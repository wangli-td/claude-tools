"""Asynchronous source management for CCM.

Provides concurrent updates for multiple sources using asyncio.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ccm.config import Config
from ccm.source import SourceManager


class AsyncSourceManager(SourceManager):
    """Source manager with async update capabilities."""

    def __init__(self, config: Config | None = None, max_workers: int = 5) -> None:
        super().__init__(config)
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def update_async(self, name: str) -> dict[str, Any]:
        """Update a source asynchronously.

        Args:
            name: Source name

        Returns:
            Update result dict
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.update, name)

    async def update_all_async(
        self, progress_callback: callable | None = None
    ) -> list[dict[str, Any]]:
        """Update all sources concurrently.

        Args:
            progress_callback: Optional callback(source_name, result) for progress updates

        Returns:
            List of update results
        """
        sources = self.list()
        if not sources:
            return []

        # Create tasks for all sources
        tasks = []
        for source in sources:
            task = self._update_with_callback(source.name, progress_callback)
            tasks.append(task)

        # Run all updates concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed = []
        for i, result in enumerate(results):
            source_name = sources[i].name
            if isinstance(result, Exception):
                processed.append({
                    "source": source_name,
                    "updated": False,
                    "error": str(result),
                })
            else:
                processed.append(result)

        return processed

    async def _update_with_callback(
        self, name: str, callback: callable | None
    ) -> dict[str, Any]:
        """Update a source and optionally call progress callback."""
        try:
            result = await self.update_async(name)
            if callback:
                callback(name, result)
            return result
        except Exception as e:
            if callback:
                callback(name, {"error": str(e)})
            raise

    def close(self) -> None:
        """Clean up executor resources."""
        self.executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
