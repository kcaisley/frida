"""``python -m flow.sweep``: ``flow.sweep.runner`` (its worker functions live there, where a spawned
process can import them; multiprocessing never imports a package's ``__main__``)."""

from flow.sweep.runner import main

main()
