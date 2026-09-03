import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')
from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile

TASKS = {
    'B3.2': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_2_config_refactor', 4, 'config.py'),
    'B3.3': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_3_enum_migration', 5, 'status.py'),
    'B3.4': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_4_typed_dict', 5, 'user_types.py'),
    'B3.5': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_5_module_restructure', 5, 'utils.py'),
}

for task_name, (task_dir, total_tests, seed_file) in TASKS.items():
    task_path = pathlib.Path(task_dir)
    best_score = 0.0

    def make_eval(td, sf, tt):
        def evaluate(program):
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = pathlib.Path(tmp)
                for f in td.glob('*.py'):
                    shutil.copy(f, tmpdir / f.name)
                (tmpdir / sf).write_text(program)
                result = subprocess.run(
                    ['python3', '-m', 'pytest', 'test_refactoring.py', '--tb=no', '-q'],
                    capture_output=True, text=True, cwd=tmpdir
                )
                lines = result.stdout.strip().split('\n')
                last = lines[-1] if lines else ''
                passed = int(last.split(' passed')[0].split()[-1]) if 'passed' in last else 0
                score = passed / tt
                return score
        return evaluate

    seed = (task_path / seed_file).read_text()
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=make_eval(task_path, seed_file, total_tests),
        objective=f"Fix {seed_file} so all pytest tests pass.",
        config=GEPAConfig(
            engine=EngineConfig(max_metric_calls=20),
            reflection=ReflectionConfig(reflection_lm='claude-opus-4-5-20251101'),
        ),
    )
    # Find best from iterations printed to stdout
    print(f"RESULT {task_name}: done")
