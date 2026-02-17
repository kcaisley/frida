.PHONY: docs docs-pdf docs-pdf-force docs-clean docs-clean-aux

docs:
	$(MAKE) -C docs docs

docs-pdf:
	$(MAKE) -C docs pdf SRC="$(SRC)"

docs-pdf-force:
	$(MAKE) -C docs pdf-force SRC="$(SRC)"

docs-clean:
	$(MAKE) -C docs clean SRC="$(SRC)"

docs-clean-aux:
	$(MAKE) -C docs clean-aux SRC="$(SRC)"
