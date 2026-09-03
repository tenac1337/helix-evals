import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')

from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile

TASK_DIR = pathlib.Path('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_1_api_versioning')

FILES = ['core.py', 'handlers.py', 'logger.py', 'serializer.py']

def evaluate(program: str) -> float:
    """Split concatenated program back into files and run tests."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        for f in TASK_DIR.glob('*.py'):
            shutil.copy(f, tmpdir / f.name)
        # Try to split by file markers and write each file
        current_file = None
        current_lines = []
        for line in program.split('\n'):
            if line.startswith('### FILE: '):
                if current_file and current_lines:
                    (tmpdir / current_file).write_text('\n'.join(current_lines))
                current_file = line.replace('### FILE: ', '').strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_file and current_lines:
            (tmpdir / current_file).write_text('\n'.join(current_lines))
        result = subprocess.run(
            ['python3', '-m', 'pytest', 'test_refactoring.py', '--tb=no', '-q'],
            capture_output=True, text=True, cwd=tmpdir
        )
        lines = result.stdout.strip().split('\n')
        last = lines[-1] if lines else ''
        passed = int(last.split(' passed')[0].split()[-1]) if 'passed' in last else 0
        return passed / 5

# Build concatenated seed
seed_parts = []
for fname in FILES:
    content = (TASK_DIR / fname).read_text()
    seed_parts.append(f"### FILE: {fname}\n{content}")
seed = '\n\n'.join(seed_parts)

print("Seed (concat):")
print(seed[:200])
print("...")

result = optimize_anything(
    seed_candidate=seed,
    evaluator=evaluate,
    objective="Fix the failing tests. The files are concatenated with ### FILE: markers. Return the full concatenated program with all files fixed.",
    config=GEPAConfig(
        engine=EngineConfig(max_metric_calls=20),
        reflection=ReflectionConfig(reflection_lm='claude-opus-4-5-20251101'),
    ),
)

print(f"GEPA concat B3.1 best score: {result.best_candidate_score if hasattr(result, 'best_candidate_score') else 'check result'}")
