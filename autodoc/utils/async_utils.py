import asyncio
import logging
from typing import List, Coroutine, Any, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')

async def run_concurrent_tasks(
    coroutines: List[Coroutine[Any, Any, T]],
    concurrency_limit: int,
    task_name_prefix: str = "concurrent_task",
    return_exceptions: bool = False
) -> List[Any]:
    """
    Runs a list of awaitable tasks concurrently with a specified limit.

    Args:
        coroutines: A list of coroutine objects to run.
        concurrency_limit: The maximum number of tasks to run simultaneously.
        task_name_prefix: A prefix for naming the asyncio tasks (useful for debugging).
        return_exceptions: If True, exceptions from coroutines are returned as
                           results instead of raising. Defaults to False.

    Returns:
        A list containing the results or exceptions (if return_exceptions=True)
        from the coroutines, in the order they were provided.
    """
    if not coroutines:
        return []

    if concurrency_limit <= 0:
        raise ValueError("Concurrency limit must be greater than 0")

    semaphore = asyncio.Semaphore(concurrency_limit)
    tasks = []
    results = [None] * len(coroutines) 

    async def _worker(index: int, coro: Coroutine[Any, Any, T]):
        """Acquires semaphore, runs coroutine, releases semaphore, stores result."""
        task_name = f"{task_name_prefix}_{index}"
        try:
            current_task = asyncio.current_task()
            if current_task:
                current_task.set_name(task_name)
        except Exception: 
            pass

        logger.debug(f"Task {task_name} waiting for semaphore...")
        async with semaphore:
            logger.debug(f"Task {task_name} acquired semaphore, starting execution.")
            try:
                result = await coro
                results[index] = result 
                logger.debug(f"Task {task_name} finished successfully.")
            except Exception as e:
                logger.error(f"Task {task_name} failed with exception: {e}", exc_info=False) 
                if return_exceptions:
                    results[index] = e 
                else:
                    raise 
            finally:
                 logger.debug(f"Task {task_name} releasing semaphore.")


    logger.info(f"Starting {len(coroutines)} tasks with concurrency limit {concurrency_limit}...")

    for i, coro in enumerate(coroutines):
        tasks.append(asyncio.create_task(_worker(i, coro)))

    await asyncio.gather(*tasks, return_exceptions=return_exceptions)

    logger.info(f"Finished running {len(coroutines)} tasks.")
    return results

# Example Usage (for testing purposes, not part of the main util)
# async def sample_task(duration: float, task_id: int) -> str:
#     print(f"Task {task_id} started, sleeping for {duration}s")
#     await asyncio.sleep(duration)
#     if task_id == 3:
#          raise ValueError(f"Task {task_id} encountered an error!")
#     print(f"Task {task_id} finished.")
#     return f"Result from task {task_id}"

# async def main():
#     tasks_to_run = [
#         sample_task(1.5, 1),
#         sample_task(0.5, 2),
#         sample_task(1.0, 3), # This one will raise an error
#         sample_task(0.8, 4),
#         sample_task(1.2, 5),
#     ]
#     limit = 2

#     print("--- Running with return_exceptions=True ---")
#     results_with_exceptions = await run_concurrent_tasks(tasks_to_run, limit, return_exceptions=True)
#     print("Results (including exceptions):", results_with_exceptions)
#     for i, res in enumerate(results_with_exceptions):
#         if isinstance(res, Exception):
#             print(f"Task {i+1} failed: {type(res).__name__}: {res}")
#         else:
#             print(f"Task {i+1} succeeded: {res}")

#     print("\n--- Running with return_exceptions=False ---")
#     try:
#         results_without_exceptions = await run_concurrent_tasks(tasks_to_run, limit, return_exceptions=False)
#         print("Results (should not be reached if error occurs):", results_without_exceptions)
#     except Exception as e:
#         print(f"Caught expected exception: {type(e).__name__}: {e}")


# if __name__ == "__main__":
#     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
#     asyncio.run(main())