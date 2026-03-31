PYTHON ?= python3

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

run:
	streamlit run app.py

test:
	pytest -q

generate-outputs:
	$(PYTHON) -m src.generate_outputs
