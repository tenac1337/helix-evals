import numpy as np
from scipy.optimize import minimize

def solve(objective_function, config, best_xs=None):
    bounds = np.array(config['bounds'])
    budget = config.get('budget', 2000)
    n_restarts = min(10, budget // 50)
    all_attempts = []
    best_x = None
    best_score = float('inf')

    for _ in range(n_restarts):
        x0 = np.random.uniform(bounds[:, 0], bounds[:, 1])
        try:
            res = minimize(
                lambda x: float(objective_function(x)),
                x0, method='L-BFGS-B',
                bounds=[(b[0], b[1]) for b in bounds],
                options={'maxfun': budget // n_restarts}
            )
            x, s = res.x, res.fun
        except Exception:
            x = x0
            s = float(objective_function(x0))
        all_attempts.append({"x": x.tolist(), "score": float(s)})
        if s < best_score:
            best_score = s
            best_x = x.copy()

    return {"x": best_x, "score": float(best_score), "all_attempts": all_attempts}
