"""Run every existing and analytical unittest module, including nested folders."""
import importlib.util
import argparse
import json
from pathlib import Path
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='outputs/analytics/test_results.json')
    args = parser.parse_args()
    suite = unittest.TestSuite()
    modules = {}
    for path in sorted((ROOT/'tests').rglob('test_*.py')):
        name = '_'.join(path.relative_to(ROOT).with_suffix('').parts)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        group = unittest.defaultTestLoader.loadTestsFromModule(module)
        modules[path.relative_to(ROOT).as_posix()] = group.countTestCases()
        suite.addTests(group)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    evidence = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                    skipped=len(result.skipped), seconds=time.perf_counter()-started, modules=modules)
    path = ROOT/args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
