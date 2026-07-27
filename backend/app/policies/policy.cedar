permit(
  principal == Agent::"agent-alpha",
  action in [PaymentAction::"initiate_transfer"],
  resource == MerchantCategory::"travel"
) when {
  context.amount <= principal.effective_cap &&
  context.epoch == principal.current_epoch &&
  (context.amount <= principal.base_cap * 0.2 || context.dual_control_approved == true)
};
