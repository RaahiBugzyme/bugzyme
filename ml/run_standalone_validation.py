"""HeartMatch ML V3 — Standalone Validation Script.

Executes standalone validation workflow across all 10 recommendation scenarios,
isolated temporary persistence audit, and baseline vs personalized ranking comparisons.
"""
from dating_ml_model.standalone_validation import (
    StandaloneValidationRunner,
    format_validation_report_text,
)

if __name__ == "__main__":
    runner = StandaloneValidationRunner()
    results = runner.run_all_scenarios()
    print(format_validation_report_text(results))
