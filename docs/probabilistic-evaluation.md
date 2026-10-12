# Probabilistic model evaluation — experimental infrastructure

This is a pure evaluation module, **not a trained wildfire model**. `fire_public.model_evaluation.evaluate_binary` measures supplied, independently labeled binary predictions against a *pre-specified* reference probability using Brier score, Brier skill score, log loss and reliability bins. It never derives fire truth from FIRMS satellite candidates.

Data contract: each record supplies `event_id`, `region_id`, `decision_at`, `label_available_at`, `label` (0/1), `prediction`, `baseline_prediction` and `split="test"`. Records with a non-test split, invalid probability, duplicate (event, decision time), or labels known at/before decision time are rejected.

**Limits of validation:** This interface cannot independently verify that features, model fitting or constant baseline estimation used only past data. Dataset builders **must** separately prove independent labels, forecast issue/availability times, group-aware train/test disjointness, geographic and calendar holdout policies, and label completeness. `label_available_at > decision_at` is necessary for many prospective targets but is not sufficient to prevent leakage. Do not publish any real-world prediction or probability until these checks and meaningful independent evaluation exist. Do not infer world-wide transferability from regional performance.

Run:
```sh
python -m unittest discover -s tests -p 'test_model_evaluation.py' -v
```

Tests use explicit synthetic fixtures to validate implementation only; fixture performance is **not** measured wildfire model accuracy. The next vertical slice is a real historical independently labeled event dataset with as-of feature join and strict geographic/event/time holdout, followed by a persistence or base-rate model and fully documented calibration.
