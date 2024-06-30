venv:
	python -m venv venv
	venv/bin/pip install -r requirements.txt

run:
	venv/bin/python clubbot.py
