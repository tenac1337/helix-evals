GPU_MEM_SIZE = 80  # GB

# EVOLVE-BLOCK-START

def compute_model_placement(gpu_num, models):
    """
    Compute a model placement that minimizes the maximum KVPR across all GPUs.
    Uses improved greedy (post-placement KVPR metric) + multiple orderings + local search.
    """
    if not models:
        return {gpu_id: [] for gpu_id in range(gpu_num)}

    n = len(models)
    mw = [m.req_rate / m.slo for m in models]
    ms = [m.model_size for m in models]

    def kvpr(w, s):
        rem = GPU_MEM_SIZE - s
        return w / rem if rem > 0 else float('inf')

    def greedy(order):
        mem = [0.0] * gpu_num
        wgt = [0.0] * gpu_num
        asgn = [-1] * n
        for idx in order:
            w, s = mw[idx], ms[idx]
            best_g, best_v = -1, float('inf')
            for g in range(gpu_num):
                if mem[g] + s <= GPU_MEM_SIZE:
                    rem = GPU_MEM_SIZE - mem[g] - s
                    v = (wgt[g] + w) / rem if rem > 0 else float('inf')
                    if v < best_v:
                        best_v, best_g = v, g
            if best_g == -1:
                return None
            asgn[idx] = best_g
            mem[best_g] += s
            wgt[best_g] += w
        return asgn, mem, wgt

    def local_search(asgn, mem, wgt):
        asgn = list(asgn)
        mem = list(mem)
        wgt = list(wgt)
        kv = [kvpr(wgt[g], mem[g]) for g in range(gpu_num)]

        while True:
            cur_max = max(kv)
            best_gain, best_op = 1e-12, None

            for i in range(n):
                gi = asgn[i]
                wi, si = mw[i], ms[i]

                for gj in range(gpu_num):
                    if gj == gi or mem[gj] + si > GPU_MEM_SIZE:
                        continue
                    k_gi = kvpr(wgt[gi] - wi, mem[gi] - si)
                    k_gj = kvpr(wgt[gj] + wi, mem[gj] + si)
                    new_max = max(k_gi, k_gj)
                    for g in range(gpu_num):
                        if g != gi and g != gj and kv[g] > new_max:
                            new_max = kv[g]
                    gain = cur_max - new_max
                    if gain > best_gain:
                        best_gain, best_op = gain, ('m', i, gi, gj)

                for j in range(i + 1, n):
                    gj = asgn[j]
                    if gj == gi:
                        continue
                    wj, sj = mw[j], ms[j]
                    nm_i = mem[gi] - si + sj
                    nm_j = mem[gj] - sj + si
                    if nm_i > GPU_MEM_SIZE or nm_j > GPU_MEM_SIZE:
                        continue
                    nw_i = wgt[gi] - wi + wj
                    nw_j = wgt[gj] - wj + wi
                    k_i = kvpr(nw_i, nm_i)
                    k_j = kvpr(nw_j, nm_j)
                    new_max = max(k_i, k_j)
                    for g in range(gpu_num):
                        if g != gi and g != gj and kv[g] > new_max:
                            new_max = kv[g]
                    gain = cur_max - new_max
                    if gain > best_gain:
                        best_gain, best_op = gain, ('s', i, j, gi, gj)

            if best_op is None:
                break

            if best_op[0] == 'm':
                _, i, gi, gj = best_op
                wi, si = mw[i], ms[i]
                wgt[gi] -= wi; mem[gi] -= si
                wgt[gj] += wi; mem[gj] += si
                asgn[i] = gj
                kv[gi] = kvpr(wgt[gi], mem[gi])
                kv[gj] = kvpr(wgt[gj], mem[gj])
            else:
                _, i, j, gi, gj = best_op
                wi, si = mw[i], ms[i]
                wj, sj = mw[j], ms[j]
                nm_i = mem[gi] - si + sj
                nm_j = mem[gj] - sj + si
                nw_i = wgt[gi] - wi + wj
                nw_j = wgt[gj] - wj + wi
                mem[gi], mem[gj] = nm_i, nm_j
                wgt[gi], wgt[gj] = nw_i, nw_j
                asgn[i], asgn[j] = gj, gi
                kv[gi] = kvpr(nw_i, nm_i)
                kv[gj] = kvpr(nw_j, nm_j)

        return asgn, mem, wgt

    orderings = [
        list(range(n)),
        sorted(range(n), key=lambda i: mw[i], reverse=True),
        sorted(range(n), key=lambda i: ms[i], reverse=True),
        sorted(range(n), key=lambda i: mw[i] * ms[i], reverse=True),
        sorted(range(n), key=lambda i: mw[i] / (ms[i] + 1e-9), reverse=True),
        sorted(range(n), key=lambda i: ms[i] + mw[i], reverse=True),
        sorted(range(n), key=lambda i: mw[i], reverse=False),
        sorted(range(n), key=lambda i: ms[i], reverse=False),
    ]

    best_asgn = None
    best_val = float('inf')

    for ordering in orderings:
        result = greedy(ordering)
        if result is None:
            continue
        asgn, mem, wgt = local_search(*result)
        v = max(kvpr(wgt[g], mem[g]) for g in range(gpu_num))
        if v < best_val:
            best_val = v
            best_asgn = list(asgn)

    if best_asgn is None:
        raise ValueError(
            f"Unable to place models on {gpu_num} GPUs. "
            f"Model sizes: {ms}"
        )

    placement = {g: [] for g in range(gpu_num)}
    for i, g in enumerate(best_asgn):
        placement[g].append(models[i])
    return placement

# EVOLVE-BLOCK-END


if __name__ == "__main__":
    from evaluator import generate_test_gpu_models
    from evaluator import calculate_kvcache_pressure
    from evaluator import safe_float
    import numpy as np

    test_cases = generate_test_gpu_models()
    all_kvpr = []
    for i, (gpu_num, gpu_models) in enumerate(test_cases):
        results = compute_model_placement(gpu_num, gpu_models)
        max_kvpr = calculate_kvcache_pressure(results)
        all_kvpr.append(safe_float(max_kvpr))

    avg_kvpr = np.mean(all_kvpr)
    if avg_kvpr != 0:
        avg_kvpr = 1.0 / avg_kvpr

    print(f"Max KVPR: {avg_kvpr:.3f}")