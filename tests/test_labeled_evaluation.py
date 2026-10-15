"""Synthetic fixtures audit software behavior; never report model accuracy as real."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from fire_public.labeled_evaluation import run_evaluation

MANIFEST={
    "schema_version":1,"target_name":"Independently adjudicated event in study area",
    "target_definition":"An externally adjudicated wildfire outcome for sampled event units",
    "horizon_hours":24,"unit_of_analysis":"One sampled region decision and independent outcome",
    "study_region":"Explicitly delimited experimental regions",
    "labeling_protocol":"Manual adjudication by an independent reviewer",
    "positive_label_rule":"Documented independently adjudicated wildfire occurrence",
    "negative_label_rule":"Independently checked complete outcome registry and confirmed no target in sampled unit",
    "sampling_frame":"Independent enumerated region/time sampling frame",
    "negative_coverage_audited":True,"independent_label_provenance_verified":True,
    "ground_truth_source_url":"https://example.org/registry",
    "rights_url":"https://example.org/rights","prepared_by":"Test fixture creator",
    "prepared_at":"2026-10-12T20:00:00Z"
}

def case(i,decision,label,region='A',available=None):
    available=available or ('2026-09-04T00:00:00Z' if decision.startswith('2026-09') else
                            '2026-10-12T00:00:00Z')
    return {"event_id":f"event-{i}","region_id":region,"decision_at":decision,
        "feature_cutoff_at":decision,"label_available_at":available,
        "label_verified_at":available,"label":label,
        "label_source":"independent-test-registry","label_source_id":f"registry-{i}",
        "label_evidence_url":f"https://example.org/outcome/{i}",
        "case_sampling_id":f"sampling-{i}"}

class LabeledEvaluationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.manifest=self.root/'manifest.json'
        self.cohort=self.root/'cases.jsonl'
        self.manifest.write_text(json.dumps(MANIFEST))
        self.rows=[
            case(1,'2026-09-01T00:00:00Z',0),
            case(2,'2026-09-01T00:00:00Z',1),
            case(3,'2026-09-02T00:00:00Z',1),
            case(4,'2026-09-02T00:00:00Z',0),
            case(5,'2026-10-10T00:00:00Z',1),
            case(6,'2026-10-10T00:00:00Z',0)]
        self.save()
    def save(self):
        self.cohort.write_text(''.join(json.dumps(r)+'\n' for r in self.rows))
    def evaluate(self,**kwargs):
        return run_evaluation(self.cohort,self.manifest,
            test_start='2026-10-01T00:00:00Z',**kwargs)

    def test_reproducible_as_of_baseline_with_audit_hashes(self):
        result=self.evaluate()
        self.assertEqual(result['label_audit']['positive'],3)
        self.assertEqual(result['experiment']['train_n'],4)
        self.assertEqual(result['experiment']['test_n'],2)
        self.assertEqual(result['experiment']['fit_rate'],0.5)
        self.assertEqual(result['experiment']['evaluation']['brier_score'],0.25)
        self.assertEqual(result['cohort_sha256'],hashlib.sha256(self.cohort.read_bytes()).hexdigest())
        self.assertEqual(result['scientific_status'],
                         'audited_input_baseline_not_independently_revalidated')

    def test_test_labels_cannot_influence_fit(self):
        before=self.evaluate()['experiment']['fit_rate']
        self.rows[-1]['label']=1;self.save()
        self.assertEqual(self.evaluate()['experiment']['fit_rate'],before)

    def test_source_manifest_must_audit_negative_coverage(self):
        for key in ('negative_coverage_audited','independent_label_provenance_verified'):
            changed=dict(MANIFEST,**{key:False})
            self.manifest.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,key):
                self.evaluate()
        self.manifest.write_text(json.dumps(MANIFEST))

    def test_deny_unsafe_negative_ground_truth_rule(self):
        changed=dict(MANIFEST,negative_label_rule="Missing from active agency layer means no wildfire")
        self.manifest.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'not independent'):
            self.evaluate()

    def test_deny_thermal_pseudolabels(self):
        self.rows[0]['label_source']='firms';self.save()
        with self.assertRaisesRegex(ValueError,'satellite pixels'):
            self.evaluate()

    def test_feature_future_and_label_time_leakage(self):
        self.rows[0]['feature_cutoff_at']='2026-09-05T00:00:00Z';self.save()
        with self.assertRaisesRegex(ValueError,'feature-time leakage'):
            self.evaluate()
        self.rows[0]['feature_cutoff_at']=self.rows[0]['decision_at']
        self.rows[0]['label_available_at']=self.rows[0]['decision_at'];self.save()
        with self.assertRaisesRegex(ValueError,'label acquisition chronology'):
            self.evaluate()

    def test_no_training_repeated_identity_and_single_class_fail(self):
        with self.assertRaises(ValueError):
            run_evaluation(self.cohort,self.manifest,test_start='2026-01-01T00:00:00Z')
        self.rows[1]['event_id']=self.rows[0]['event_id'];self.save()
        with self.assertRaisesRegex(ValueError,'duplicate decision event'):
            self.evaluate()
        for i,r in enumerate(self.rows):
            r['event_id']=f"event-{i}"
            r['label']=1
        self.save()
        with self.assertRaisesRegex(ValueError,'both independently verified'):
            self.evaluate()

    def test_spatial_holdout_excludes_heldout_training_history(self):
        self.rows[0]['region_id']='B'
        self.rows[4]['region_id']='B'
        self.rows[5]['region_id']='B'
        self.save()
        result=self.evaluate(heldout_regions=('B',))
        self.assertEqual(result['experiment']['test_n'],2)
        self.assertEqual(result['experiment']['train_n'],3)
        self.assertGreater(result['experiment']['split']['excluded_by_reason']['heldout_region_history'],0)

    def test_cli_report_is_private_and_refuses_overwrite(self):
        output=self.root/'summary.json'
        cmd=[sys.executable,'-m','fire_public.labeled_evaluation',
             '--cohort',str(self.cohort),'--manifest',str(self.manifest),
             '--test-start','2026-10-01T00:00:00Z','--output',str(output)]
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        doc=json.loads(output.read_text())
        self.assertEqual(doc['experiment']['test_n'],2)
        self.assertNotIn('registry-5',output.read_text())
        duplicate=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(duplicate.returncode,0)
        unsafe=cmd[:]
        unsafe[-1]=str(self.cohort)
        blocked=subprocess.run(unsafe,capture_output=True,text=True)
        self.assertNotEqual(blocked.returncode,0)
        self.assertEqual(len(self.cohort.read_text().splitlines()),6)


    def test_feature_audit_is_reported_and_future_data_blocked(self):
        for r in self.rows:
            r["features"] = {"temperature": {
                "value": 24,
                "observed_at": r["decision_at"],
                "available_at": r["decision_at"],
                "source_id": "synthetic-weather-receipt"}}
        self.save()
        result = self.evaluate()
        self.assertEqual(result["feature_availability_audit"]["eligible"], 6)
        self.assertFalse(result["feature_availability_audit"]["model_training_authorized"])
        self.rows[0]["features"]["temperature"]["available_at"] = "2026-12-01T00:00:00Z"
        self.save()
        with self.assertRaisesRegex(ValueError, "Feature as-of"):
            self.evaluate()

    def test_missing_feature_evidence_is_explicit_not_a_pass(self):
        result = self.evaluate()
        self.assertIsNone(result["feature_availability_audit"])
        self.rows[0]["features"] = {"temperature": {
            "value": 24, "observed_at": self.rows[0]["decision_at"],
            "available_at": self.rows[0]["decision_at"],
            "source_id": "synthetic"}}
        self.save()
        with self.assertRaisesRegex(ValueError, "Partial feature evidence"):
            self.evaluate()

if __name__=='__main__':
    unittest.main()
