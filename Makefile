.PHONY: run venv debug

venv:
	rm -rf venv
	python -m venv venv
	venv/bin/pip install -r requirements.txt

run:
	rm -f runtime.log
	venv/bin/python clubbot.py 2>&1

debug:
	venv/bin/python -m pdb clubbot.py
