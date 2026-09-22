"""Fixed-charge supplier allocation, with one supplier per consolidated SKU line."""
from itertools import product
from time import perf_counter
from ortools.sat.python import cp_model


def eligible_options(lines, quotes, max_days=365):
    options, failures = [], []
    for line in lines:
        candidates = [q for q in quotes if q["sku_id"] == line["sku_id"] and q.get("available_quantity") is not None and q["available_quantity"] >= line["quantity"] >= q.get("min_quantity", 1) and q.get("lead_days", 0) <= max_days]
        options.append(candidates)
        if not candidates:
            failures.append({"sku_id": line["sku_id"], "reason": "无已审核有效且满足数量、起订量和交期的报价；未知库存须人工确认"})
    return options, failures


def summarize(lines, selected, status, elapsed=0, bound=None):
    suppliers = {}
    allocation = []
    for line, quote in zip(lines, selected):
        mid = quote["merchant_id"]
        # A supplier charges its maximum published freight once for this order.
        suppliers[mid] = max(suppliers.get(mid, 0), quote.get("freight", 0))
        allocation.append({"sku_id": line["sku_id"], "quantity": line["quantity"], "quote_id": quote["id"], "quote_version": quote.get("version", 1), "merchant_id": mid, "unit_cost": quote["price"], "goods_cost": line["quantity"] * quote["price"], "lead_days": quote.get("lead_days", 0)})
    goods = sum(a["goods_cost"] for a in allocation)
    shipping = sum(suppliers.values())
    return {"status": status, "allocation": allocation, "goods_cost": goods, "freight": shipping, "total_cost": goods + shipping, "supplier_count": len(suppliers), "supplier_freight": suppliers, "lead_days": max((a["lead_days"] for a in allocation), default=0), "elapsed_ms": elapsed * 1000, "best_bound": bound}


def solve(lines, quotes, max_days=365, max_suppliers=None, budget=None, time_limit=3.0):
    start = perf_counter()
    if not lines: return {"status": "INFEASIBLE", "reasons": [{"reason": "订单不能为空"}]}
    if len({x['sku_id'] for x in lines}) != len(lines):
        raise ValueError("Consolidate duplicate SKU demand before solving")
    options, failures = eligible_options(lines, quotes, max_days)
    if failures: return {"status": "INFEASIBLE", "reasons": failures, "elapsed_ms": (perf_counter() - start) * 1000}
    model = cp_model.CpModel()
    choices = {(i, j): model.new_bool_var(f"x_{i}_{j}") for i, row in enumerate(options) for j in range(len(row))}
    merchant_ids = sorted({q["merchant_id"] for row in options for q in row})
    active = {mid: model.new_bool_var(f"y_{mid}") for mid in merchant_ids}
    shipping = {}
    for mid in merchant_ids:
        selected = [(choices[i, j], q["freight"]) for i, row in enumerate(options) for j, q in enumerate(row) if q["merchant_id"] == mid]
        for variable, _ in selected: model.add(variable <= active[mid])
        model.add(active[mid] <= sum(variable for variable, _ in selected))
        shipping[mid] = model.new_int_var(0, max(f for _, f in selected), f"freight_{mid}")
        model.add_max_equality(shipping[mid], [var * freight for var, freight in selected])
    for i, row in enumerate(options): model.add_exactly_one(choices[i, j] for j in range(len(row)))
    total = sum(choices[i, j] * lines[i]["quantity"] * q["price"] for i, row in enumerate(options) for j, q in enumerate(row)) + sum(shipping.values())
    if max_suppliers is not None: model.add(sum(active.values()) <= max_suppliers)
    if budget is not None: model.add(total <= budget)
    model.minimize(total)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    result = solver.solve(model)
    status = solver.status_name(result)
    elapsed = perf_counter() - start
    if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status, "reasons": [{"reason": "供应商数量或预算约束不可满足" if result == cp_model.INFEASIBLE else "限时内未找到可行方案"}], "elapsed_ms": elapsed * 1000}
    selected = [next(q for j, q in enumerate(row) if solver.value(choices[i, j])) for i, row in enumerate(options)]
    return summarize(lines, selected, status, elapsed, solver.best_objective_bound)


def greedy(lines, quotes, prefer_fewer=False, max_days=365):
    start = perf_counter()
    options, failures = eligible_options(lines, quotes, max_days)
    if failures: return {"status": "INFEASIBLE", "reasons": failures}
    paid_freight, selected = {}, []
    for line, row in zip(lines, options):
        def incremental_cost(quote):
            extra_freight = max(0, quote.get("freight", 0) - paid_freight.get(quote["merchant_id"], 0))
            return (quote["price"] * line["quantity"] + (extra_freight if prefer_fewer else 0), quote["id"])
        choice = min(row, key=incremental_cost)
        selected.append(choice)
        mid = choice["merchant_id"]
        paid_freight[mid] = max(paid_freight.get(mid, 0), choice.get("freight", 0))
    return summarize(lines, selected, "HEURISTIC", perf_counter() - start)


def exhaustive(lines, quotes, max_days=365, max_suppliers=None, budget=None):
    options, failures = eligible_options(lines, quotes, max_days)
    if failures: return None
    best = None
    for selected in product(*options):
        candidate = summarize(lines, selected, "OPTIMAL")
        if max_suppliers is not None and candidate["supplier_count"] > max_suppliers: continue
        if budget is not None and candidate["total_cost"] > budget: continue
        if best is None or candidate["total_cost"] < best["total_cost"]: best = candidate
    return best
