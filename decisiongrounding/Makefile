.PHONY: demo test compare

# The one working comparison: two real arms, four worked scenarios, offline.
demo:
	python -m runner.cli demo

# Run a single named comparison, e.g. make compare ARMS=context_dump,naive_rag
compare:
	python -m runner.cli compare --arms $(ARMS)

test:
	python -m pytest -q
