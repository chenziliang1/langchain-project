# Model Artifacts

This private project package includes the final Transformer-Hawkes Process forecast model and the local training/evaluation artifacts used during development.

Key files:

- `thp_gdelt.pt`: final checkpoint loaded by the Forecast page and forecast API.
- `thp_training_dataset.npz`: cached training arrays used to train the model.
- `thp_calibration_dataset_seq14_h7.npz`: calibration/evaluation arrays.
- `training_logs/`: JSONL/CSV-style training logs and run metadata.
- `thp_sweeps/`: hyperparameter sweep outputs and intermediate checkpoints.

The model can be loaded through `backend/services/thp_neural.py` and is exposed through the FastAPI data forecast route.
