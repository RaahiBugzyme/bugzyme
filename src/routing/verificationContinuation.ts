/**
 * Only a Vite development build may expose the manual-review continuation.
 * The production gate remains based on the backend's verified status.
 */
export function shouldOfferDevelopmentVerificationContinuation(
  developmentBuild: boolean,
  pendingReview: boolean,
) {
  return developmentBuild && pendingReview
}
