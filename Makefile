.PHONY: install-dev format format-check lint test build-dist release-check check

VERSION := $(shell python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

install-dev:
	python -m pip install -e ".[dev]"

format:
	find alphalab -name "*.py" -print0 | xargs -0 -n1 black --quiet

format-check:
	find alphalab -name "*.py" -print0 | xargs -0 -n1 black --check --quiet

lint:
	ruff check alphalab

test:
	python -m unittest discover -s alphalab/tests -p "test_*.py"

build-dist:
	python -m build --no-isolation

release-check: check
	@grep -q "^## \[$(VERSION)\]" CHANGELOG.md || (echo "CHANGELOG missing version $(VERSION) section" && exit 1)

check: format-check lint test
