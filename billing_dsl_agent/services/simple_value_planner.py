"""Simple AST value planner for MVP DSL generation chain."""

from __future__ import annotations

from typing import Any

from billing_dsl_agent.types.common import ContextScope
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, ValuePlan
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import BOBinding, ContextBinding, FunctionBinding, ResolvedEnvironment, ResourceBinding


class SimpleValuePlanner:
    """Build minimal ValuePlan from intent/binding/env with deterministic rules."""

    def build_plan(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ValuePlan:
        """Build a runnable ValuePlan AST for the target node."""

        mapping_expr = self._build_conditional_mapping_expr(intent=intent, binding=binding)
        if mapping_expr is not None:
            return ValuePlan(target_node_path=intent.target_node_path, methods=[], final_expr=mapping_expr)

        base_expr = self._build_base_expr(intent=intent, binding=binding, env=env)
        wrapped_expr = self._wrap_function_if_needed(base_expr=base_expr, intent=intent, binding=binding, env=env)
        final_expr = self._wrap_conditional_if_needed(expr=wrapped_expr, intent=intent, binding=binding)

        return ValuePlan(
            target_node_path=intent.target_node_path,
            methods=[],
            final_expr=final_expr or ExprNode(kind=ExprKind.LITERAL, value=""),
        )

    def _build_conditional_mapping_expr(self, intent: NodeIntent, binding: ResourceBinding) -> ExprNode | None:
        """Build conditional mapping IF expression from semantic slots and semantic binding."""

        slots = intent.semantic_slots or {}
        if not slots.get("conditional_mapping"):
            return None

        field_path = binding.semantic_bindings.get("condition_field")
        if not field_path:
            field_hint = str(slots.get("condition_field_hint", "") or "")
            if field_hint:
                field_path = self._field_hint_to_fallback_path(field_hint)

        left_expr = self._build_ref_expr_from_path(field_path or "$ctx$.conditionField")
        operator = str(slots.get("condition_operator", "==") or "==")
        condition_value = slots.get("condition_value", "")

        cond_expr = ExprNode(
            kind=ExprKind.BINARY_OP,
            value=operator,
            children=[
                left_expr,
                ExprNode(kind=ExprKind.LITERAL, value=condition_value),
            ],
        )

        true_expr = ExprNode(kind=ExprKind.LITERAL, value=slots.get("true_output", ""))
        false_expr = ExprNode(kind=ExprKind.LITERAL, value=slots.get("false_output", ""))
        return ExprNode(kind=ExprKind.IF_EXPR, children=[cond_expr, true_expr, false_expr])

    def _build_base_expr(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ExprNode:
        """Build base expression from context/query hints before function/if wrapping."""

        if IntentSourceType.BO_QUERY in intent.source_types or IntentSourceType.NAMING_SQL in intent.source_types:
            bo_binding = self._pick_bo_binding(binding, intent)
            if bo_binding is not None:
                query_expr = self._build_query_expr(bo_binding)
                if bo_binding.selected_field_names:
                    return ExprNode(
                        kind=ExprKind.FIELD_ACCESS,
                        value=bo_binding.selected_field_names[0],
                        children=[query_expr],
                    )
                return query_expr

        if IntentSourceType.CONTEXT in intent.source_types:
            global_binding = self._find_context_binding(binding, ContextScope.GLOBAL)
            if global_binding:
                return self._build_context_expr(global_binding)
            if len(env.global_context_vars) == 1:
                return self._build_context_expr(
                    ContextBinding(var_name=env.global_context_vars[0].name, scope=ContextScope.GLOBAL)
                )

        if IntentSourceType.LOCAL_CONTEXT in intent.source_types:
            local_binding = self._find_context_binding(binding, ContextScope.LOCAL)
            if local_binding:
                return self._build_local_expr(local_binding)
            if len(env.local_context_vars) == 1:
                return self._build_local_expr(
                    ContextBinding(var_name=env.local_context_vars[0].name, scope=ContextScope.LOCAL)
                )

        bo_binding = self._pick_bo_binding(binding, intent)
        if bo_binding is not None:
            query_expr = self._build_query_expr(bo_binding)
            if bo_binding.selected_field_names:
                return ExprNode(
                    kind=ExprKind.FIELD_ACCESS,
                    value=bo_binding.selected_field_names[0],
                    children=[query_expr],
                )
            return query_expr

        if IntentSourceType.CONTEXT in intent.source_types and len(env.global_context_vars) == 1:
            return ExprNode(kind=ExprKind.CONTEXT_REF, value=f"$ctx$.{env.global_context_vars[0].name}")

        if IntentSourceType.LOCAL_CONTEXT in intent.source_types and len(env.local_context_vars) == 1:
            return ExprNode(kind=ExprKind.LOCAL_REF, value=f"$local$.{env.local_context_vars[0].name}")

        return ExprNode(kind=ExprKind.LITERAL, value="")

    def _wrap_function_if_needed(
        self,
        base_expr: ExprNode,
        intent: NodeIntent,
        binding: ResourceBinding,
        env: ResolvedEnvironment,
    ) -> ExprNode:
        """Wrap expression with function call when function binding/candidate exists."""

        if IntentSourceType.FUNCTION not in intent.source_types and not binding.function_bindings:
            return base_expr

        function_binding = self._pick_function_binding(binding=binding, env=env)
        if function_binding is None:
            return base_expr

        function_name = (
            f"{function_binding.class_name}.{function_binding.method_name}"
            if function_binding.class_name
            else function_binding.method_name
        )
        arg_expr = base_expr or ExprNode(kind=ExprKind.LITERAL, value="")

        args: list[ExprNode] = [arg_expr]
        precision = intent.semantic_slots.get("format_precision")
        if precision is not None:
            args.append(ExprNode(kind=ExprKind.LITERAL, value=precision))

        return ExprNode(
            kind=ExprKind.FUNCTION_CALL,
            value=function_name,
            children=args,
        )

    def _wrap_conditional_if_needed(self, expr: ExprNode, intent: NodeIntent, binding: ResourceBinding) -> ExprNode:
        """Build IF expression when conditional source type exists."""

        if IntentSourceType.CONDITIONAL not in intent.source_types:
            return expr

        cond_expr = self._build_cond_expr(binding=binding)
        true_expr = expr
        false_expr = ExprNode(kind=ExprKind.LITERAL, value="")
        return ExprNode(kind=ExprKind.IF_EXPR, children=[cond_expr, true_expr, false_expr])

    def _build_cond_expr(self, binding: ResourceBinding) -> ExprNode:
        """Build a minimal condition expression from known bindings."""

        local_binding = self._find_context_binding(binding, ContextScope.LOCAL)
        if local_binding:
            return self._build_local_expr(local_binding)

        global_binding = self._find_context_binding(binding, ContextScope.GLOBAL)
        if global_binding:
            return self._build_context_expr(global_binding)

        return ExprNode(kind=ExprKind.LITERAL, value=True)

    @staticmethod
    def _pick_bo_binding(binding: ResourceBinding, intent: NodeIntent) -> BOBinding | None:
        """Select BO binding preferring one-value query modes."""

        if not binding.bo_bindings:
            return None

        for candidate in binding.bo_bindings:
            if candidate.query_mode.value in {"SELECT_ONE", "FETCH_ONE"}:
                return candidate

        if IntentSourceType.BO_QUERY in intent.source_types or IntentSourceType.NAMING_SQL in intent.source_types:
            return binding.bo_bindings[0]

        return binding.bo_bindings[0]

    @staticmethod
    def _build_query_expr(bo_binding: BOBinding) -> ExprNode:
        """Build query call AST node from BO binding."""

        target = bo_binding.naming_sql_name or bo_binding.bo_name
        query_mode = bo_binding.query_mode.value.lower()
        children = [ExprNode(kind=ExprKind.LITERAL, value=True)] if query_mode.startswith("select") else []
        return ExprNode(
            kind=ExprKind.QUERY_CALL,
            metadata={"query_mode": query_mode, "target": target},
            children=children,
        )

    @staticmethod
    def _find_context_binding(binding: ResourceBinding, scope: ContextScope) -> ContextBinding | None:
        """Find first context binding by scope."""

        return next((item for item in binding.context_bindings if item.scope == scope), None)

    @staticmethod
    def _build_context_expr(context_binding: ContextBinding) -> ExprNode:
        """Build global context AST expression with optional field access."""

        base = ExprNode(kind=ExprKind.CONTEXT_REF, value=f"$ctx$.{context_binding.var_name}")
        if context_binding.field_name:
            return ExprNode(kind=ExprKind.FIELD_ACCESS, value=context_binding.field_name, children=[base])
        return base

    @staticmethod
    def _build_local_expr(context_binding: ContextBinding) -> ExprNode:
        """Build local context AST expression with optional field access."""

        base = ExprNode(kind=ExprKind.LOCAL_REF, value=f"$local$.{context_binding.var_name}")
        if context_binding.field_name:
            return ExprNode(kind=ExprKind.FIELD_ACCESS, value=context_binding.field_name, children=[base])
        return base

    @staticmethod
    def _pick_function_binding(binding: ResourceBinding, env: ResolvedEnvironment) -> FunctionBinding | None:
        """Pick a function binding; fallback to singleton function in environment."""

        if binding.function_bindings:
            return binding.function_bindings[0]

        if len(env.available_functions) == 1:
            fn = env.available_functions[0]
            return FunctionBinding(class_name=fn.class_name, method_name=fn.method_name)

        return None

    @staticmethod
    def _field_hint_to_fallback_path(field_hint: str) -> str:
        """Convert field hint into conservative fallback context path."""

        token = "".join(ch for ch in field_hint if ch.isalnum() or ch == "_") or "conditionField"
        return f"$ctx$.{token}"

    @staticmethod
    def _build_ref_expr_from_path(path: str) -> ExprNode:
        """Build context/local reference expr from path, optionally with field access."""

        if path.startswith("$local$."):
            tail = path[len("$local$.") :]
            return SimpleValuePlanner._build_ref_with_field_access(ExprKind.LOCAL_REF, "$local$", tail)

        if path.startswith("$ctx$."):
            tail = path[len("$ctx$.") :]
            return SimpleValuePlanner._build_ref_with_field_access(ExprKind.CONTEXT_REF, "$ctx$", tail)

        return ExprNode(kind=ExprKind.CONTEXT_REF, value=path)

    @staticmethod
    def _build_ref_with_field_access(kind: ExprKind, prefix: str, tail: str) -> ExprNode:
        """Build reference expression by splitting var and optional field path."""

        parts = [p for p in (tail or "").split(".") if p]
        if not parts:
            return ExprNode(kind=kind, value=prefix)

        base = ExprNode(kind=kind, value=f"{prefix}.{parts[0]}")
        current = base
        for field_name in parts[1:]:
            current = ExprNode(kind=ExprKind.FIELD_ACCESS, value=field_name, children=[current])
        return current
