"""Pure Decimal arithmetic over a bounded DAG. No eval, code, I/O or tax constants."""
from decimal import Decimal, localcontext, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP
import re

from app.schemas.formula import FormulaPlan


class FormulaError(ValueError):
    pass


def number(value):
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,18}(?:\.\d{1,12})?", value):
        raise FormulaError("invalid_decimal")
    result = Decimal(value)
    if not result.is_finite() or abs(result) > Decimal('1e18'):
        raise FormulaError("numeric_limit")
    return result


def _same_units(units):
    if len(set(units)) != 1:
        raise FormulaError("incompatible_units")
    return units[0]


def execute(plan: FormulaPlan):
    values, units = {}, {}
    tables = {table.id: table for table in plan.tables}
    if len(tables) != len(plan.tables):
        raise FormulaError("duplicate_table")
    for table in plan.tables:
        lower = Decimal(0)
        for index, band in enumerate(table.bands):
            rate = number(band.rate)
            if not 0 <= rate <= 1:
                raise FormulaError("invalid_rate")
            if band.upper is None:
                if index != len(table.bands) - 1:
                    raise FormulaError("unbounded_middle_band")
            else:
                upper = number(band.upper)
                if upper <= lower:
                    raise FormulaError("unordered_bands")
                lower = upper
    for entry in plan.values:
        if entry.id in values:
            raise FormulaError("duplicate_value")
        values[entry.id], units[entry.id] = number(entry.value), entry.unit
    trace = []
    with localcontext() as ctx:
        ctx.prec = 50
        for step in plan.steps:
            if step.id in values:
                raise FormulaError("duplicate_step")
            if any(key not in values for key in step.args):
                raise FormulaError("unknown_or_forward_reference")
            args = [values[key] for key in step.args]
            dims = [units[key] for key in step.args]
            unary = step.op in {'progressive', 'round'}
            binary = step.op in {'subtract', 'divide'}
            if (unary and len(args) != 1 or binary and len(args) != 2
                    or not unary and not binary and len(args) < 2):
                raise FormulaError("invalid_arity")
            if step.op in {'add', 'subtract', 'min', 'max'}:
                unit = _same_units(dims)
                if step.op == 'add': result = sum(args, Decimal(0))
                elif step.op == 'subtract': result = args[0] - args[1]
                elif step.op == 'min': result = min(args)
                else: result = max(args)
            elif step.op == 'multiply':
                if dims.count('KRW') > 1:
                    raise FormulaError("money_squared")
                result = Decimal(1)
                for value in args: result *= value
                unit = 'KRW' if 'KRW' in dims else 'ratio' if 'ratio' in dims else 'count'
            elif step.op == 'divide':
                if args[1] == 0 or dims[1] == 'KRW' and dims[0] != 'KRW':
                    raise FormulaError("invalid_division")
                result = args[0] / args[1]
                unit = 'ratio' if dims[0] == dims[1] else dims[0]
            elif step.op == 'progressive':
                if dims != ['KRW'] or args[0] < 0 or step.table_id not in tables:
                    raise FormulaError("invalid_progressive_input")
                table = tables[step.table_id]
                if table.bands[-1].upper is not None and args[0] > number(table.bands[-1].upper):
                    raise FormulaError("incomplete_rate_table")
                lower, result = Decimal(0), Decimal(0)
                for band in table.bands:
                    upper = number(band.upper) if band.upper is not None else args[0]
                    result += max(Decimal(0), min(args[0], upper) - lower) * number(band.rate)
                    lower = upper
                unit = 'KRW'
            else:
                result, unit = args[0], dims[0]
                if step.rounding == 'none':
                    raise FormulaError("missing_rounding_mode")
            if step.rounding != 'none':
                if unit != 'KRW':
                    raise FormulaError("rounding_non_money")
                result = result.quantize(Decimal(1), rounding={
                    'floor_won': ROUND_FLOOR, 'truncate_won': ROUND_DOWN,
                    'nearest_won': ROUND_HALF_UP}[step.rounding])
            if not result.is_finite() or abs(result) > Decimal('1e18'):
                raise FormulaError("numeric_limit")
            values[step.id], units[step.id] = result, unit
            trace.append({'id': step.id, 'label': step.label, 'op': step.op,
                          'args': step.args, 'value': format(result, 'f'), 'unit': unit,
                          'rule_ids': step.rule_ids, 'rounding': step.rounding})
    outputs = []
    for output in plan.outputs:
        if output.step_id not in {step.id for step in plan.steps} or units[output.step_id] != 'KRW':
            raise FormulaError("invalid_output")
        value = values[output.step_id]
        if output.role != 'balance' and value < 0:
            raise FormulaError("negative_tax_or_prepaid")
        outputs.append(output.model_dump() | {'value': format(value, 'f')})
    roles = {role: [Decimal(o['value']) for o in outputs if o['role'] == role]
             for role in ('total', 'component', 'prepaid', 'balance')}
    if len(roles['total']) != 1 or len(roles['prepaid']) > 1 or len(roles['balance']) > 1:
        raise FormulaError("invalid_output_roles")
    if roles['component'] and sum(roles['component']) != roles['total'][0]:
        raise FormulaError("component_total_mismatch")
    if bool(roles['prepaid']) != bool(roles['balance']):
        raise FormulaError("missing_prepaid_or_balance")
    if roles['prepaid'] and roles['total'][0] - roles['prepaid'][0] != roles['balance'][0]:
        raise FormulaError("balance_mismatch")
    return {'steps': trace, 'outputs': outputs}
