.PHONY: install ingest run test

export PYTHONPATH := $(shell pwd)

install:
	python3 -m pip install -r requirements.txt

ingest:
	python3 -c "from ingestion.load import run_ingestion_pipeline; from app.config import PDF_PATH; run_ingestion_pipeline(PDF_PATH)"

run:
	PYTHONPATH=$(shell pwd) python3 -m streamlit run app/app.py

test:
	pytest tests/ -v

all: install ingest run