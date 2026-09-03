import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')

from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile

TASKS = {
    'B3.2': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_2_config_refactor', 'config.py', 4),
    'B3.3': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_3_enum_migration', 'status.py', 5),
    'B3.4': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_4_typed_dict', 'user_types.py', 5),
    'B3.5': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_5_module_restructure', 'utils.py', 5),
}

for task_name, (task_dir, seed_file, total_tests) in TASKS.items():
    task_path = pathlib.Path(task_dir)

    def make_evaluator(td, sf, tt):
        def evaluate(program: str) -> float:
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
                return passed / tt
        return evaluate

    seed = (task_path / seed_file).read_text()
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=make_evaluator(task_path, seed_file, total_tests),
        objective=f"Fix {seed_file} so all pytest tests pass.",
        config=GEPAConfig(
            engine=EngineConfig(max_metric_calls=20),
            reflection=ReflectionConfig(reflection_lm='claude-opus-4-5-20251101'),
        ),
    )
    # Get best score from result
    best = result.best_candidate_score if hasattr(result, 'best_candidate_score') else 'unknown'
    print(f"{task_name} per-file best score: {best}")
