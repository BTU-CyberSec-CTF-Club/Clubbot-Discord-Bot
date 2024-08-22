.PHONY: run debug

venv: requirements.txt
	rm -rf venv
	python3 -m venv venv
	venv/bin/pip install -r requirements.txt

run: venv
	venv/bin/python3 clubbot.py 2>&1

debug: venv
	venv/bin/python3 -m pdb clubbot.py

clean:
	rm -rf __pycache__ venv
