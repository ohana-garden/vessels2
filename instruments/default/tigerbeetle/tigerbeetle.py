#!/usr/bin/env python3
"""
TigerBeetle financial transactions instrument for Vessels.
Provides double-entry bookkeeping operations.
"""

import argparse
import os
import sys
import uuid

try:
    import tigerbeetle  # type: ignore
except ImportError:
    print("TigerBeetle not installed. Installing...")
    os.system("pip install tigerbeetle")
    import tigerbeetle  # type: ignore


def get_client():
    """Get TigerBeetle client connection."""
    host = os.environ.get("TIGERBEETLE_HOST", "127.0.0.1")
    port = int(os.environ.get("TIGERBEETLE_PORT", "3000"))
    cluster_id = int(os.environ.get("TIGERBEETLE_CLUSTER_ID", "0"))

    return tigerbeetle.Client(cluster_id, [f"{host}:{port}"])


def uuid_to_int(uuid_str: str) -> int:
    """Convert UUID string to 128-bit integer."""
    if uuid_str.isdigit():
        return int(uuid_str)
    return uuid.UUID(uuid_str).int


def create_account(args):
    """Create a new account."""
    client = get_client()

    account_id = uuid_to_int(args.id) if args.id else uuid.uuid4().int

    account = tigerbeetle.Account(
        id=account_id,
        debits_pending=0,
        debits_posted=0,
        credits_pending=0,
        credits_posted=0,
        user_data_128=args.user_data or 0,
        user_data_64=0,
        user_data_32=0,
        ledger=args.ledger,
        code=args.code,
        flags=(
            (tigerbeetle.AccountFlags.DEBITS_MUST_NOT_EXCEED_CREDITS if args.no_overdraft else 0) |
            (tigerbeetle.AccountFlags.CREDITS_MUST_NOT_EXCEED_DEBITS if args.liability else 0) |
            (tigerbeetle.AccountFlags.LINKED if args.linked else 0)
        ),
        timestamp=0,
    )

    errors = client.create_accounts([account])

    if errors:
        for error in errors:
            print(f"Error creating account: {error.result}")
        sys.exit(1)

    print(f"Account created successfully. ID: {account_id}")
    return account_id


def transfer(args):
    """Create a transfer between accounts."""
    client = get_client()

    transfer_id = uuid_to_int(args.id) if args.id else uuid.uuid4().int

    xfer = tigerbeetle.Transfer(
        id=transfer_id,
        debit_account_id=uuid_to_int(args.debit_account),
        credit_account_id=uuid_to_int(args.credit_account),
        amount=args.amount,
        pending_id=0,
        user_data_128=args.user_data or 0,
        user_data_64=0,
        user_data_32=0,
        timeout=0,
        ledger=args.ledger,
        code=args.code,
        flags=tigerbeetle.TransferFlags.LINKED if args.linked else 0,
        timestamp=0,
    )

    errors = client.create_transfers([xfer])

    if errors:
        for error in errors:
            print(f"Error creating transfer: {error.result}")
        sys.exit(1)

    print(f"Transfer created successfully. ID: {transfer_id}")
    print(f"  Debit: {args.debit_account} -> Credit: {args.credit_account}")
    print(f"  Amount: {args.amount}")
    return transfer_id


def pending_transfer(args):
    """Create a two-phase pending transfer."""
    client = get_client()

    transfer_id = uuid_to_int(args.id) if args.id else uuid.uuid4().int

    xfer = tigerbeetle.Transfer(
        id=transfer_id,
        debit_account_id=uuid_to_int(args.debit_account),
        credit_account_id=uuid_to_int(args.credit_account),
        amount=args.amount,
        pending_id=0,
        user_data_128=args.user_data or 0,
        user_data_64=0,
        user_data_32=0,
        timeout=args.timeout or 0,
        ledger=args.ledger,
        code=args.code,
        flags=tigerbeetle.TransferFlags.PENDING,
        timestamp=0,
    )

    errors = client.create_transfers([xfer])

    if errors:
        for error in errors:
            print(f"Error creating pending transfer: {error.result}")
        sys.exit(1)

    print(f"Pending transfer created. ID: {transfer_id}")
    print("Use 'post_transfer' or 'void_transfer' to complete.")
    return transfer_id


def post_transfer(args):
    """Post a pending transfer."""
    client = get_client()

    post_id = uuid.uuid4().int

    xfer = tigerbeetle.Transfer(
        id=post_id,
        debit_account_id=0,
        credit_account_id=0,
        amount=0,
        pending_id=uuid_to_int(args.id),
        user_data_128=0,
        user_data_64=0,
        user_data_32=0,
        timeout=0,
        ledger=0,
        code=0,
        flags=tigerbeetle.TransferFlags.POST_PENDING_TRANSFER,
        timestamp=0,
    )

    errors = client.create_transfers([xfer])

    if errors:
        for error in errors:
            print(f"Error posting transfer: {error.result}")
        sys.exit(1)

    print(f"Transfer {args.id} posted successfully.")


def void_transfer(args):
    """Void a pending transfer."""
    client = get_client()

    void_id = uuid.uuid4().int

    xfer = tigerbeetle.Transfer(
        id=void_id,
        debit_account_id=0,
        credit_account_id=0,
        amount=0,
        pending_id=uuid_to_int(args.id),
        user_data_128=0,
        user_data_64=0,
        user_data_32=0,
        timeout=0,
        ledger=0,
        code=0,
        flags=tigerbeetle.TransferFlags.VOID_PENDING_TRANSFER,
        timestamp=0,
    )

    errors = client.create_transfers([xfer])

    if errors:
        for error in errors:
            print(f"Error voiding transfer: {error.result}")
        sys.exit(1)

    print(f"Transfer {args.id} voided successfully.")


def lookup_account(args):
    """Lookup account details and balance."""
    client = get_client()

    account_id = uuid_to_int(args.id)
    accounts = client.lookup_accounts([account_id])

    if not accounts:
        print(f"Account {args.id} not found.")
        sys.exit(1)

    account = accounts[0]

    print(f"Account: {account.id}")
    print(f"  Ledger: {account.ledger}")
    print(f"  Code: {account.code}")
    print(f"  Debits Pending: {account.debits_pending}")
    print(f"  Debits Posted: {account.debits_posted}")
    print(f"  Credits Pending: {account.credits_pending}")
    print(f"  Credits Posted: {account.credits_posted}")
    print(f"  Balance: {account.credits_posted - account.debits_posted}")


def lookup_transfer(args):
    """Lookup transfer details."""
    client = get_client()

    transfer_id = uuid_to_int(args.id)
    transfers = client.lookup_transfers([transfer_id])

    if not transfers:
        print(f"Transfer {args.id} not found.")
        sys.exit(1)

    xfer = transfers[0]

    print(f"Transfer: {xfer.id}")
    print(f"  Debit Account: {xfer.debit_account_id}")
    print(f"  Credit Account: {xfer.credit_account_id}")
    print(f"  Amount: {xfer.amount}")
    print(f"  Ledger: {xfer.ledger}")
    print(f"  Code: {xfer.code}")
    print(f"  Timestamp: {xfer.timestamp}")


def main():
    parser = argparse.ArgumentParser(
        description="TigerBeetle financial transactions instrument"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create account
    create_parser = subparsers.add_parser("create_account", help="Create a new account")
    create_parser.add_argument("--id", help="Account ID (UUID or integer)")
    create_parser.add_argument("--ledger", type=int, required=True, help="Ledger ID")
    create_parser.add_argument("--code", type=int, required=True, help="Account code")
    create_parser.add_argument("--user-data", type=int, help="User data (128-bit)")
    create_parser.add_argument("--no-overdraft", action="store_true", help="Prevent overdrafts")
    create_parser.add_argument("--liability", action="store_true", help="Liability account")
    create_parser.add_argument("--linked", action="store_true", help="Link with next account")
    create_parser.set_defaults(func=create_account)

    # Transfer
    transfer_parser = subparsers.add_parser("transfer", help="Create a transfer")
    transfer_parser.add_argument("--id", help="Transfer ID (UUID or integer)")
    transfer_parser.add_argument("--debit-account", required=True, help="Debit account ID")
    transfer_parser.add_argument("--credit-account", required=True, help="Credit account ID")
    transfer_parser.add_argument("--amount", type=int, required=True, help="Amount")
    transfer_parser.add_argument("--ledger", type=int, required=True, help="Ledger ID")
    transfer_parser.add_argument("--code", type=int, required=True, help="Transfer code")
    transfer_parser.add_argument("--user-data", type=int, help="User data")
    transfer_parser.add_argument("--linked", action="store_true", help="Link with next transfer")
    transfer_parser.set_defaults(func=transfer)

    # Pending transfer
    pending_parser = subparsers.add_parser("pending_transfer", help="Create pending transfer")
    pending_parser.add_argument("--id", help="Transfer ID")
    pending_parser.add_argument("--debit-account", required=True, help="Debit account ID")
    pending_parser.add_argument("--credit-account", required=True, help="Credit account ID")
    pending_parser.add_argument("--amount", type=int, required=True, help="Amount")
    pending_parser.add_argument("--ledger", type=int, required=True, help="Ledger ID")
    pending_parser.add_argument("--code", type=int, default=0, help="Transfer code")
    pending_parser.add_argument("--timeout", type=int, help="Timeout in seconds")
    pending_parser.add_argument("--user-data", type=int, help="User data")
    pending_parser.set_defaults(func=pending_transfer)

    # Post transfer
    post_parser = subparsers.add_parser("post_transfer", help="Post a pending transfer")
    post_parser.add_argument("--id", required=True, help="Pending transfer ID")
    post_parser.set_defaults(func=post_transfer)

    # Void transfer
    void_parser = subparsers.add_parser("void_transfer", help="Void a pending transfer")
    void_parser.add_argument("--id", required=True, help="Pending transfer ID")
    void_parser.set_defaults(func=void_transfer)

    # Lookup account
    lookup_acc_parser = subparsers.add_parser("lookup_account", help="Lookup account")
    lookup_acc_parser.add_argument("--id", required=True, help="Account ID")
    lookup_acc_parser.set_defaults(func=lookup_account)

    # Lookup transfer
    lookup_xfer_parser = subparsers.add_parser("lookup_transfer", help="Lookup transfer")
    lookup_xfer_parser.add_argument("--id", required=True, help="Transfer ID")
    lookup_xfer_parser.set_defaults(func=lookup_transfer)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
