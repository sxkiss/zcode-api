/**
 * Auth manager — resolves the upstream credential from the OAuth login flow.
 * @see .omo/plans/zcode-proxy.md Task 4
 *
 * Multi-credential pool (v4.7): the manager holds N credentials and serves a
 * round-robin rotation. On an upstream 401 the failed account is
 * transiently blacklisted (`markFailed`) so the next request falls through to
 * another account instead of hammering the dead one; `getCredential` always
 * returns a single credential so call sites (proxy hot path, claim, responses,
 * async) are unchanged.
 */
import type { Credential } from "./types.js";
import { isExpired, credentialKey } from "./types.js";

const FAILOVER_COOLDOWN_MS = 120_000;

export class AuthManager {
  private creds: Credential[] = [];
  private rrIndex = 0;
  /** apiKey -> timestamp until which the account is taken out of rotation. */
  private blacklist = new Map<string, number>();

  /**
   * Returns the next healthy credential (round-robin) or throws when none is
   * available. Expired credentials are skipped and — when nothing healthy is
   * left — evicted (the first `getCredential` after full expiry throws with
   * `expired`, subsequent ones with `not available`).
   */
  async getCredential(): Promise<Credential> {
    const n = this.creds.length;
    const now = Date.now();
    for (let i = 0; i < n; i++) {
      const idx = (this.rrIndex + i) % n;
      const c = this.creds[idx];
      if (isExpired(c, now)) continue;
      const until = this.blacklist.get(credentialKey(c));
      if (until !== undefined && until > now) continue;
      this.rrIndex = (idx + 1) % n;
      return c;
    }
    const expired = this.creds.filter((c) => isExpired(c, Date.now()));
    if (expired.length > 0) {
      this.creds = this.creds.filter((c) => !isExpired(c, Date.now()));
      throw new Error("OAuth credential expired; re-authentication required — run: zcode-proxy auth login");
    }
    throw new Error("OAuth credential not available — run: zcode-proxy auth login");
  }

  /** Single-credential replacement (kept for `auth login` and legacy callers). */
  setOAuthCredential(cred: Credential): void {
    this.creds = [cred];
    this.blacklist.clear();
    this.rrIndex = 0;
  }

  /** Prime the whole pool from the store (serve path). */
  setCredentials(list: Credential[]): void {
    this.creds = [...list];
    this.blacklist = new Map();
    this.rrIndex = 0;
  }

  /** Add or replace one account in the pool without disturbing the rest. */
  addCredential(cred: Credential): void {
    const key = credentialKey(cred);
    const idx = this.creds.findIndex((c) => credentialKey(c) === key);
    if (idx >= 0) this.creds[idx] = cred;
    else this.creds.push(cred);
    this.blacklist?.delete(key);
  }

  /**
   * Record an upstream 401 for one account: take it out of rotation for
   * `cooldownMs` so the pool falls through to other accounts. With a single
   * credential this simply makes `getCredential` throw (`not available`).
   */
  markFailed(cred: Credential, cooldownMs: number = FAILOVER_COOLDOWN_MS): void {
    const key = credentialKey(cred);
    if (!this.creds.some((c) => credentialKey(c) === key)) return;
    this.blacklist.set(key, Date.now() + cooldownMs);
    if (this.creds.length > 1) {
      const now = Date.now();
      const blacklisted = [...this.blacklist.values()].filter((v) => v > now).length;
      console.warn(
        `[auth] account ${(cred.apiKey || cred.userId || "?").slice(0, 12)}… flagged failed for ${(cooldownMs / 1000).toFixed(0)}s — pool health ${this.creds.length - blacklisted}/${this.creds.length}`,
      );
    }
  }

  /** Pool snapshot for `auth status`. */
  summary(): { total: number; healthy: number; blacklisted: number } {
    const now = Date.now();
    const blacklisted = [...this.creds].filter((c) => (this.blacklist.get(credentialKey(c)) ?? 0) > now).length;
    return { total: this.creds.length, healthy: this.creds.length - blacklisted, blacklisted };
  }
}