# SmartEyes — common commands
# Usage: make help

SHELL := /bin/bash
ROOT  := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ENV   ?= smarteyes
PY    := conda run -n $(ENV) --no-capture-output python

SOURCE  ?= macbook
MICRO   ?=
BACKEND ?= yolo
EXTRA   ?=

.DEFAULT_GOAL := help

.PHONY: help demo demo-closed demo-custom demo-eyes demo-spell demo-micro \
	list-mics list-cameras capture clean-clinic prepare-hp train-hp \
	calibrate smoke check-env

help: ## Show targets
	@echo "SmartEyes Makefile (conda env: $(ENV))"
	@echo ""
	@echo "Variables: SOURCE=$(SOURCE)  BACKEND=$(BACKEND)  MICRO=$(MICRO)  EXTRA='...'"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

check-env: ## Verify conda env smarteyes exists
	@conda env list | grep -qE '^$(ENV)\s' || \
		(echo "Missing env '$(ENV)'. Run: conda env create -f environment.yml"; exit 1)

# --- Demo ---

demo: check-env ## Full MVP demo (closed-set headphones)
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --source $(SOURCE) \
		--hp-backend yolo $(EXTRA)

demo-closed: demo ## Alias for closed-set demo

demo-custom: check-env ## Full demo with closed-set over_ear weights
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --source $(SOURCE) \
		--hp-backend custom $(EXTRA)

demo-eyes: check-env ## Eyes-only desk mode
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --source $(SOURCE) \
		--eyes $(EXTRA)

demo-spell: check-env ## Spell-only (no zone/HP/eyes gate)
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --source $(SOURCE) \
		--spell $(EXTRA)

demo-micro: check-env ## Full demo + spell; set MICRO=6 or MICRO="MacBook Air"
	@test -n "$(MICRO)" || (echo 'Set MICRO, e.g. make demo-micro MICRO=6'; exit 1)
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --source $(SOURCE) \
		--micro "$(MICRO)" --hp-backend $(BACKEND) $(EXTRA)

list-mics: check-env ## List microphones
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --list-mics

list-cameras: check-env ## List cameras
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py --list-cameras

calibrate: check-env ## Calibrate stand-zone / floor
	cd $(ROOT) && $(PY) scripts/calibrate_line.py --source $(SOURCE) $(EXTRA)

smoke: check-env ## Offline eyes smoke on sample video
	cd $(ROOT) && $(PY) scripts/run_webcam_demo.py \
		--source data/sample/smoke.mp4 --no-display --eyes $(EXTRA)

# --- Headphones dataset / train (edge) ---

capture: check-env ## Capture clinic frames for labeling
	cd $(ROOT) && $(PY) scripts/capture_headphones_frames.py \
		--source $(SOURCE) --every 5 $(EXTRA)

clean-clinic: check-env ## Head-crop teacher labels + hard negatives → clinic_clean
	cd $(ROOT) && $(PY) scripts/clean_clinic_headphones_dataset.py $(EXTRA)

prepare-hp: check-env ## Merge YOLO exports → datasets/headphones/merged
	cd $(ROOT) && $(PY) scripts/prepare_headphones_dataset.py \
		--sources clinic_clean $(EXTRA)

train-hp: check-env ## Train closed-set YOLOv8n + export ONNX
	cd $(ROOT) && $(PY) scripts/train_headphones_yolo.py $(EXTRA)
