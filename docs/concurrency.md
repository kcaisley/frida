in python, there are two types of parallelism:

multi-threading vs multi-processing

the ram impact of python threads is less than multi processing

multithreading shows > 100% CPU usage on one processing

process pool executor
threadpoolexecutor

In pure python, you're limited to a single thread essentially (due to the GIL), but if you use JIT w/ numba or other precombined libraries like numpy or cython, you can safely release the GIL.

julia has parrallel computering, asyncrhonous programming, multi-threading, multi-processing and distributed computer


concurrency and/or parrallelism are two models in programming
