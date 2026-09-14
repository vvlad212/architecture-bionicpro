import ast
import unittest
from pathlib import Path


class DagSourceTest(unittest.TestCase):
    def test_dag_is_valid_python_and_has_required_stages(self) -> None:
        source = Path("airflow/dags/bionicpro_reporting.py").read_text()

        ast.parse(source)
        self.assertIn('schedule="0 0 * * *"', source)
        self.assertIn("sync_crm_customers", source)
        self.assertIn("build_daily_report_mart", source)
        self.assertIn("reporting_state", source)


if __name__ == "__main__":
    unittest.main()
