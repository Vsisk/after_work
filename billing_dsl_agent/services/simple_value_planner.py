"""Simple AST value planner for MVP DSL generation chain."""

from __future__ import annotations

from billing_dsl_agent.types.common import ContextScope, QueryMode
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, ValuePlan
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import BOBinding, ContextBinding, FunctionBinding, ResolvedEnvironment, ResourceBinding


class SimpleValuePlanner:
    """Build runnable ValuePlan AST from intent, bindings and environment."""

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

    def _build_base_expr(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ExprNode:
        """Build the primary expression before function/conditional wrapping."""

        query_expr = self._build_query_based_expr(intent=intent, binding=binding)
        if query_expr is not None:
            return query_expr

        local_expr = self._build_scope_context_expr(binding=binding, env=env, scope=ContextScope.LOCAL)
        if local_expr is not None and IntentSourceType.LOCAL_CONTEXT in intent.source_types:
            return local_expr

        global_expr = self._build_scope_context_expr(binding=binding, env=env, scope=ContextScope.GLOBAL)
        if global_expr is not None and IntentSourceType.CONTEXT in intent.source_types:
            return global_expr

        if local_expr is not None:
            return local_expr
        if global_expr is not None:
            return global_expr

        return ExprNode(kind=ExprKind.LITERAL, value="")

    def _build_query_based_expr(self, intent: NodeIntent, binding: ResourceBinding) -> ExprNode | None:
        """Build select/fetch expression when BO or namingSQL bindings exist."""

        if IntentSourceType.BO_QUERY not in intent.source_types and IntentSourceType.NAMING_SQL not in intent.source_types:
            return None

        bo_binding = self._pick_bo_binding(binding, intent)
        if bo_binding is None:
            return None

        query_expr = self._build_query_expr(bo_binding)
        if bo_binding.selected_field_names:
            return ExprNode(
                kind=ExprKind.FIELD_ACCESS,
                value=bo_binding.selected_field_names[0],
                children=[query_expr],
            )
        return query_expr

    def _build_scope_context_expr(
        self,
        binding: ResourceBinding,
        env: ResolvedEnvironment,
        scope: ContextScope,
    ) -> ExprNode | None:
        """Build direct context/local reference expression."""

        preferred = self._find_context_binding(binding, scope)
        if preferred is not None:
            return self._build_context_ref_expr(preferred)

        context_vars = env.local_context_vars if scope == ContextScope.LOCAL else env.global_context_vars
        if len(context_vars) == 1:
            return self._build_context_ref_expr(ContextBinding(var_name=context_vars[0].name, scope=scope))

        return None

    def _wrap_function_if_needed(
        self,
        base_expr: ExprNode,
        intent: NodeIntent,
        binding: ResourceBinding,
        env: ResolvedEnvironment,
    ) -> ExprNode:
        """Wrap the base expression with a function call when needed."""

        if IntentSourceType.FUNCTION not in intent.source_types and not binding.function_bindings:
            return base_expr

        function_binding = self._pick_function_binding(binding=binding, env=env)
        if function_binding is None:
            return base_expr

        args: list[ExprNode] = [base_expr]
        for arg in intent.semantic_slots.get("function_args_hint") or []:
            literal_arg = self._normalize_function_hint_arg(arg)
            if literal_arg is None:
                continue
            if literal_arg.kind == ExprKind.LITERAL and base_expr.kind == ExprKind.LITERAL and literal_arg.value == base_expr.value:
                continue
            if literal_arg.kind == ExprKind.LITERAL and isinstance(literal_arg.value, str) and literal_arg.value == "value":
                continue
            if literal_arg.kind == ExprKind.LITERAL and literal_arg.value == intent.semantic_slots.get("format_precision"):
                continue
            if literal_arg.kind == ExprKind.LITERAL and isinstance(literal_arg.value, str):
                if literal_arg.value in {"amount", "prepareId", "billCycleId", "name", "gender"}:
                    continue
            args.append(literal_arg)

        precision = intent.semantic_slots.get("format_precision")
        if precision is not None and not any(
            child.kind == ExprKind.LITERAL and child.value == precision for child in args[1:]
        ):
            args.append(ExprNode(kind=ExprKind.LITERAL, value=precision))

        function_name = (
            f"{function_binding.class_name}.{function_binding.method_name}"
            if function_binding.class_name
            else function_binding.method_name
        )
        return ExprNode(kind=ExprKind.FUNCTION_CALL, value=function_name, children=args)

    def _wrap_conditional_if_needed(self, expr: ExprNode, intent: NodeIntent, binding: ResourceBinding) -> ExprNode:
        """Build IF expression when conditional source type exists."""

        if IntentSourceType.CONDITIONAL not in intent.source_types:
            return expr

        cond_expr = self._build_cond_expr(intent=intent, binding=binding)
        if cond_expr is None:
            return expr

        true_expr = self._build_literal_or_expr(intent.semantic_slots.get("true_output"), fallback=expr)
        false_expr = self._build_literal_or_expr(intent.semantic_slots.get("false_output"), fallback=ExprNode(kind=ExprKind.LITERAL, value=""))
        return ExprNode(kind=ExprKind.IF_EXPR, children=[cond_expr, true_expr, false_expr])

    def _build_conditional_mapping_expr(self, intent: NodeIntent, binding: ResourceBinding) -> ExprNode | None:
        """Build conditional mapping IF expression from semantic slots and semantic binding."""

        slots = intent.semantic_slots or {}
        if not slots.get("conditional_mapping"):
            return None

        cond_expr = self._build_cond_expr(intent=intent, binding=binding)
        if cond_expr is None:
            return None

        true_expr = ExprNode(kind=ExprKind.LITERAL, value=slots.get("true_output", ""))
        false_expr = ExprNode(kind=ExprKind.LITERAL, value=slots.get("false_output", ""))
        return ExprNode(kind=ExprKind.IF_EXPR, children=[cond_expr, true_expr, false_expr])

    def _build_cond_expr(self, intent: NodeIntent, binding: ResourceBinding) -> ExprNode | None:
        """Build a binary conditional expression from semantic slots."""

        slots = intent.semantic_slots or {}
        condition_path = binding.semantic_bindings.get("condition_field")
        if not condition_path:
            condition_hint = str(slots.get("condition_field_hint", "") or "")
            if condition_hint:
                condition_path = self._field_hint_to_fallback_path(condition_hint)

        if not condition_path:
            local_binding = self._find_context_binding(binding, ContextScope.LOCAL)
            if local_binding is not None:
                condition_path = self._binding_to_path(local_binding)
            else:
                global_binding = self._find_context_binding(binding, ContextScope.GLOBAL)
                if global_binding is not None:
                    condition_path = self._binding_to_path(global_binding)

        if not condition_path:
            return None

        operator = str(slots.get("condition_operator", "==") or "==")
        right_value = slots.get("condition_value", True)
        return ExprNode(
            kind=ExprKind.BINARY_OP,
            value=operator,
            children=[
                self._build_ref_expr_from_path(condition_path),
                ExprNode(kind=ExprKind.LITERAL, value=right_value),
            ],
        )

    @staticmethod
    def _pick_bo_binding(binding: ResourceBinding, intent: NodeIntent) -> BOBinding | None:
        """Select BO binding preferring one-value query modes."""

        if not binding.bo_bindings:
            return None

        for candidate in binding.bo_bindings:
            if candidate.query_mode in {QueryMode.SELECT_ONE, QueryMode.FETCH_ONE}:
                return candidate

        if IntentSourceType.BO_QUERY in intent.source_types or IntentSourceType.NAMING_SQL in intent.source_types:
            return binding.bo_bindings[0]

        return binding.bo_bindings[0]

    @staticmethod
    def _build_query_expr(bo_binding: BOBinding) -> ExprNode:
        """Build query call AST node from BO binding."""

        target = bo_binding.naming_sql_name or bo_binding.bo_name
        query_mode = bo_binding.query_mode.value.lower()
        return ExprNode(
            kind=ExprKind.QUERY_CALL,
            metadata={"query_mode": query_mode, "target": target},
            children=[],
        )

    @staticmethod
    def _find_context_binding(binding: ResourceBinding, scope: ContextScope) -> ContextBinding | None:
        """Find first context binding by scope."""

        return next((item for item in binding.context_bindings if item.scope == scope), None)

    @staticmethod
    def _build_context_ref_expr(context_binding: ContextBinding) -> ExprNode:
        """Build direct CONTEXT_REF or LOCAL_REF with full path as value."""

        if context_binding.scope == ContextScope.LOCAL:
            prefix = "$local$"
            kind = ExprKind.LOCAL_REF
        else:
            prefix = "$ctx$"
            kind = ExprKind.CONTEXT_REF

        path = f"{prefix}.{context_binding.var_name}"
        if context_binding.field_name:
            path = f"{path}.{context_binding.field_name}"
        return ExprNode(kind=kind, value=path)

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
    def _binding_to_path(binding: ContextBinding) -> str:
        prefix = "$local$" if binding.scope == ContextScope.LOCAL else "$ctx$"
        path = f"{prefix}.{binding.var_name}"
        if binding.field_name:
            path = f"{path}.{binding.field_name}"
        return path

    @staticmethod
    def _build_ref_expr_from_path(path: str) -> ExprNode:
        """Build direct context/local reference expr from fully-qualified path."""

        if path.startswith("$local$."):
            return ExprNode(kind=ExprKind.LOCAL_REF, value=path)
        if path.startswith("$ctx$."):
            return ExprNode(kind=ExprKind.CONTEXT_REF, value=path)
        return ExprNode(kind=ExprKind.CONTEXT_REF, value=path)

    @staticmethod
    def _normalize_function_hint_arg(arg: object) -> ExprNode | None:
        """Convert function hint args into AST nodes."""

        if arg is None:
            return None
        if isinstance(arg, ExprNode):
            return arg
        if isinstance(arg, (int, float, bool)):
            return ExprNode(kind=ExprKind.LITERAL, value=arg)
        text = str(arg).strip()
        if not text:
            return None
        if text.startswith("$ctx$.") or text.startswith("$local$."):
            return SimpleValuePlanner._build_ref_expr_from_path(text)
        return ExprNode(kind=ExprKind.LITERAL, value=text)

    @staticmethod
    def _build_literal_or_expr(value: object, fallback: ExprNode) -> ExprNode:
        """Use literal when provided, otherwise fallback expression."""

        if value is None or value == "":
            return fallback
        if isinstance(value, ExprNode):
            return value
        return ExprNode(kind=ExprKind.LITERAL, value=value)
