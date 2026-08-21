/**
 * What "Reset Product Details" actually does, said accurately.
 *
 * Reset clears the form and sets a component-state flag that stops the re-seed effect from putting the
 * demo product back. It makes no API call, and the flag does not survive a reload -- so the saved
 * product section is untouched and loads again on refresh.
 *
 * The message said the opposite: "Neo content will not return unless you load the demo examples." For a
 * teaching tool, copy that overstates what happened is worse than the behaviour it was describing.
 */

export type ProductResetOutcome = {
  tone: "warning";
  message: string;
};

export function describeProductReset({
  hasSavedProduct,
}: {
  hasSavedProduct: boolean;
}): ProductResetOutcome {
  if (hasSavedProduct) {
    return {
      tone: "warning",
      message:
        "Product details were cleared in this form. The saved version is unchanged — it will load again " +
        "if you reload the page. Add your own details and save to replace it.",
    };
  }

  return {
    tone: "warning",
    message: "Product details were cleared. Add your own details, then save when ready.",
  };
}
