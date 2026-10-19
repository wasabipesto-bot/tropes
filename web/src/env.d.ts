declare namespace App {
  interface Locals {
    /** True when the request carries a valid owner session. Always false until Phase 2. */
    owner: boolean;
  }
}
