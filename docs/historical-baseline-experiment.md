# Historical base-rate baseline (experimental)

`fire_public.historical_baseline.historical_rate_experiment` combines the existing embargoed geographic/time splitter and probability scoring. The fitted constant baseline is a Laplace-smoothed prevalence based **only on training outcomes available before the holdout cutoff**. Test data do not influence the fit. It exposes Brier score, log loss and reliability bins via `model_evaluation.py`.

Input records need `event_id`, `region_id`, `decision_at`, `label_available_at`, binary `label`, `label_source`, `label_source_id`. The caller must verify the label source is *actually independent* and that negative labels are valid, not merely absent satellite thermal signals. `label_source` alone is not an independence audit. Avoid using retrospectively revised final perimeters as contemporaneous model features. Record the sampling frame, event definition, geographic coverage, provider outages, feature availability, exclusion rates and time horizon before interpreting scores.

Current tests contain illustrative synthetic fixtures only: **no learned real wildfire prevalence or forecast has been reported**. This module makes no extra provider requests, deploys no ML model, and publishes no probabilities to the live site.

Run `python -m unittest discover -s tests -p 'test_historical_baseline.py' -v`.

Next: obtain a small licensed historical cohort of independently labeled positives and negatives with valid observation coverage, using a clearly specified spatial unit and time horizon. Build a reproducible source manifest and an as-of weather-feature join before comparing the baseline to more complex models. Results for the US or Canada must never be generalized to the world without separate evaluation.
