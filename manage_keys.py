#!/usr/bin/env python3
"""
LeadsClean API key manager — run on the server to issue, list, and revoke keys.

Usage:
  python manage_keys.py create --email user@example.com [--plan starter]
  python manage_keys.py list
  python manage_keys.py revoke <key>

Plans and monthly call limits:
  trial    100
  starter  500
  growth   2 000
  pro      10 000
"""

import argparse
import sys

from db import PLAN_LIMITS, create_key, init_db, list_keys, revoke_key


def cmd_create(args: argparse.Namespace) -> None:
    if args.plan not in PLAN_LIMITS:
        print(f"Unknown plan '{args.plan}'. Valid plans: {', '.join(PLAN_LIMITS)}")
        sys.exit(1)
    key = create_key(email=args.email, plan=args.plan)
    limit = PLAN_LIMITS[args.plan]
    print(f"\nAPI key created:")
    print(f"  Key:   {key}")
    print(f"  Email: {args.email}")
    print(f"  Plan:  {args.plan} ({limit:,} calls/month)")
    print(f"\nCopy and send this key to the user — it will NOT be shown again.\n")


def cmd_list(_args: argparse.Namespace) -> None:
    rows = list_keys()
    if not rows:
        print("No API keys found.")
        return
    header = f"{'Key':<52}  {'Email':<28}  {'Plan':<8}  {'Used':>6}/{'Limit':<7}  Reset"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['key']:<52}  {r['email']:<28}  {r['plan']:<8}  "
            f"{r['calls_used']:>6}/{r['monthly_limit']:<7}  {r['reset_at']}"
        )


def cmd_revoke(args: argparse.Namespace) -> None:
    if revoke_key(args.key):
        print(f"Revoked: {args.key}")
    else:
        print(f"Key not found: {args.key}")
        sys.exit(1)


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(
        description="LeadsClean API key manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_create = sub.add_parser("create", help="Issue a new API key")
    p_create.add_argument("--email", required=True, help="Customer email address")
    p_create.add_argument(
        "--plan",
        default="starter",
        choices=list(PLAN_LIMITS),
        help="Subscription plan (default: starter)",
    )

    sub.add_parser("list", help="List all API keys with current usage")

    p_revoke = sub.add_parser("revoke", help="Permanently revoke an API key")
    p_revoke.add_argument("key", help="The lc_... key to revoke")

    args = parser.parse_args()

    if args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "revoke":
        cmd_revoke(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
