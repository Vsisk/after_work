# ProgramPlan Migration Notes

## What Changed

The planning pipeline now uses `ProgramPlan` as the primary plan schema:

- old: `PlanDraft -> ExprNode`
- new: `ProgramPlan(definitions + return_expr) -> ProgramNode`

`ProgramPlan` is now the only primary planner output.

## New Planner Output Shape

```json
{
  "definitions": [
    {
      "kind": "variable",
      "name": "customer_gender",
      "expr": {
        "type": "query_call",
        "query_kind": "select_one",
        "source_name": "CustomerBO",
        "field": "gender",
        "filters": [
          {
            "field": "id",
            "value": {
              "type": "context_ref",
              "path": "$ctx$.customer.id"
            }
          }
        ]
      }
    }
  ],
  "return_expr": {
    "type": "var_ref",
    "name": "customer_gender"
  }
}
```

## Legacy Compatibility

Legacy planner payloads are still accepted only at parse time:

- old `PlanDraft` payloads are adapted to `ProgramPlan(definitions=[], return_expr=...)`
- `expr_tree`-only payloads are also adapted to `ProgramPlan`

Compatibility is one-way:

- planner parse may adapt legacy payloads
- validation failure does not fall back to legacy execution

## Validation Changes

Validation is now program-aware and includes:

- definition count limits
- per-definition expression depth limits
- return expression depth limit
- total node count limit
- total `if` node limit
- variable name validation
- duplicate name detection
- forward reference checks
- undefined `var_ref` checks
- definition dependency cycle detection
- explicit rejection of `kind="method"` in this phase

Validation issues are now structured objects with:

- `code`
- `message`
- `path`
- `severity`

## AST and Rendering Changes

ASTBuilder now produces `ProgramNode`:

- `definitions: list[VariableDefNode]`
- `return_node: ReturnNode`

Renderer output is now multi-line when definitions exist:

```txt
def customer_gender = select_one(CustomerBO.gender, id=$ctx$.customer.id)
def title_prefix = if(customer_gender == "M", "MR.", "MS.")
title_prefix
```

`ReturnNode` remains explicit in AST, but the rendered DSL uses the final expression line as the returned value.
