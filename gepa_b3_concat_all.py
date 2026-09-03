import sys
sys.path.insert(0, '/Users/kevinchon/Documents/Research/KDKC/gepa/src')

from gepa.optimize_anything import optimize_anything, EngineConfig, GEPAConfig, ReflectionConfig
import subprocess, pathlib, shutil, tempfile

TASKS = {
    'B3.2': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_2_config_refactor', 4, ['config.py', 'database.py', 'auth.py', 'logger.py']),
    'B3.3': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_3_enum_migration', 5, ['status.py', 'user.py', 'validator.py', 'report.py']),
    'B3.4': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_4_typed_dict', 5, ['user_types.py', 'user_service.py', 'storage.py']),
    'B3.5': ('/Users/kevinchon/Documents/Research/KDKC/b3_tasks/b3_5_module_restructure', 5, ['core.py', 'utils.py', 'pipeline.py', 'analyzer.py']),
}

for task_name, (task_dir, total_tests, files) in TASKS.items():
    task_path = pathlib.Path(task_dir)

    def make_evaluator(td, fs, tt):
        def evaluate(program: str) -> float:
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = pathlib.Path(tmp)
                for f in td.glob('*.py'):
                    shutil.copy(f, tmpdir / f.name)
                # Split program by file markers
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
                return passed / tt
        return evaluate

    seed_parts = []
    for fname in files:
        content = (task_path / fname).read_text()
        seed_parts.append(f"### FILE: {fname}\n{content}")
    seed = '\n\n'.join(seed_parts)

    print(f"\n=== {task_name} ===")
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=make_evaluator(task_path, files, total_tests),
        objective=f"Fix all files so pytest tests pass. Files use ### FILE: markers.",
        config=GEPAConfig(
            engine=EngineConfig(max_metric_calls=20),
            reflection=ReflectionConfig(reflection_lm='claude-opus-4-5-20251101'),
        ),
    )
    print(f"{task_name} concat best: check above iterations")
