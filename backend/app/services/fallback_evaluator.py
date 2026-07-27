# This file replaces cedar-policy bindings due to cedarpy failing to parse custom action types.
# Specifically, cedarpy throws: 'expected an entity uid with type `Action` but got `PaymentAction::"initiate_transfer"`'.
# Providing a strict schema to cedarpy to support custom action types is beyond the scope of a minimal setup,
# so we use this JSON-rule evaluator to emulate the exact conceptual shape of Cedar policies.

import json

class JSONRuleEvaluator:
    def __init__(self, policy_json: dict):
        self.policy = policy_json
        
    def _eval_expr(self, expr, context, principal):
        if not isinstance(expr, dict):
            return expr
        
        op = list(expr.keys())[0]
        args = expr[op]
        
        if op == "var":
            var_name = args
            if var_name.startswith("context."):
                return context.get(var_name.replace("context.", ""))
            elif var_name.startswith("principal."):
                return principal.get(var_name.replace("principal.", ""))
            return None
        
        elif op == "<=":
            left = self._eval_expr(args[0], context, principal)
            right = self._eval_expr(args[1], context, principal)
            return left <= right
            
        elif op == "==":
            left = self._eval_expr(args[0], context, principal)
            right = self._eval_expr(args[1], context, principal)
            return left == right
            
        elif op == "&&":
            return self._eval_expr(args[0], context, principal) and self._eval_expr(args[1], context, principal)
            
        elif op == "||":
            return self._eval_expr(args[0], context, principal) or self._eval_expr(args[1], context, principal)
            
        elif op == "*":
            left = self._eval_expr(args[0], context, principal)
            right = self._eval_expr(args[1], context, principal)
            return left * right
            
        return False

    def is_authorized(self, principal_id: str, action_id: str, resource_id: str, context: dict, principal_attrs: dict) -> bool:
        # Check target matching
        if self.policy.get("principal") and self.policy["principal"] != principal_id:
            return False
            
        allowed_actions = self.policy.get("action", [])
        if isinstance(allowed_actions, list):
            if action_id not in allowed_actions:
                return False
        elif action_id != allowed_actions:
            return False
            
        if self.policy.get("resource") and self.policy["resource"] != resource_id:
            return False
            
        # Check when clause
        if "when" in self.policy:
            return self._eval_expr(self.policy["when"], context, principal_attrs)
            
        return True

# Hardcoded JSON equivalent of policy.cedar
DEFAULT_POLICY_JSON = {
    "action": ['PaymentAction::"initiate_transfer"'],
    "when": {
        "&&": [
            {
                "&&": [
                    {"<=": [{"var": "context.amount"}, {"var": "principal.effective_cap"}]},
                    {"==": [{"var": "context.epoch"}, {"var": "principal.current_epoch"}]}
                ]
            },
            {
                "||": [
                    {"<=": [{"var": "context.amount"}, {"*": [{"var": "principal.base_cap"}, 0.2]}]},
                    {"==": [{"var": "context.dual_control_approved"}, True]}
                ]
            }
        ]
    }
}
