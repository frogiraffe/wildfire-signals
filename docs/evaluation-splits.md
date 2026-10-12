# Geographic and temporal evaluation splits

`fire_public.evaluation_splits.holdout_split` creates explicit train/test partitions for independently labeled event-level examples. It supports a forward-in-time cutoff, a configurable embargo, and optional held-out region IDs. It removes training records sharing an event identity with test observations and records excluded cases by reason. All timestamps must be timezone aware.

Example: `holdout_split(rows, test_start="2026-01-01T00:00:00Z", embargo_hours=72, heldout_regions=["CA-WEST"])`.

Important: This is metadata-level leakage *reduction*, not complete prevention. Geographic `region_id` boundaries must be explicit, stable and non-overlapping for the chosen claim. Regions can be adjacent and still share weather/incident spillovers. Training features require independent availability timestamps and source issue times; overlapping labels and repeated incidents must be audited. The splitter does not verify outcome provenance, label completeness, spatial independence, hyperparameter selection, train/test contamination through data preprocessing, or globally representative sampling. A successful synthetic test cannot establish model skill.

Use `python -m unittest discover -s tests -p 'test_evaluation_splits.py' -v`.

Next vertical slice: assemble a small **real independently labeled** fire-event evaluation cohort, register its provider, geographical and temporal support, prevent future information from entering features, and compare a historical base-rate reference to an interpretable predictive model. Avoid inferring wildfire non-events from missing FIRMS candidates.
