import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa')

from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile

TASK_DIR = pathlib.Path('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_1_api_versioning')

def evaluate(program: str) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        for f in TASK_DIR.glob('*.py'):
            shutil.copy(f, tmpdir / f.name)
        (tmpdir / 'core.py').write_text(program)
        result = subprocess.run(
            ['python3', '-m', 'pytest', 'test_refactoring.py', '--tb=no', '-q'],
            capture_output=True, text=True, cwd=tmpdir
        )
        lines = result.stdout.strip().split('\n')
        last = lines[-1] if lines else ''
        passed = int(last.split(' passed')[0].split()[-1]) if 'passed' in last else 0
        return passed / 5

seed = (TASK_DIR / 'core.py').read_text()

result = optimize_anything(
    seed_candidate=seed,
    evaluator=evaluate,
    objective="Fix core.py so all 5 pytest tests pass. Tests expect JSON dict format output when format='json'.",
    config=GEPAConfig(
        engine=EngineConfig(max_metric_calls=20),
        reflection=ReflectionConfig(reflection_lm='claude-opus-4-5-20251101'),
    ),
)

print(f"GEPA per-file B3.1 best score: {result.best_candidate}")
print(f"Score: {result.best_score}")
