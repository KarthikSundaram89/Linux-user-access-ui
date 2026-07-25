#!/usr/bin/env python3
"""
AWS Secrets Manager Setup Script.
Creates the secret in AWS Secrets Manager with auto-generated secure values.

Usage:
  python scripts/setup_secrets.py --create
  python scripts/setup_secrets.py --show-template
  python scripts/setup_secrets.py --verify

Requires: boto3, AWS credentials configured
"""

import argparse
import json
import secrets
import sys

SECRET_NAME = "linux-access-portal/config"
REGION = "us-east-1"


def generate_secret_template() -> dict:
    """Generate a template with secure random values."""
    return {
        "SECRET_KEY": secrets.token_hex(32),
        "SESSION_SECRET_KEY": secrets.token_hex(32),
        "ENCRYPTION_KEY": secrets.token_hex(32),
        "EMERGENCY_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "AZURE_CLIENT_SECRET": "REPLACE-WITH-YOUR-AZURE-CLIENT-SECRET",
        "SMTP_PASSWORD": "REPLACE-WITH-YOUR-SMTP-PASSWORD",
        "DATABASE_URL": "sqlite+aiosqlite:///./data/portal.db",
    }


def show_template():
    """Print the template JSON for manual creation."""
    template = generate_secret_template()
    print("\n=== AWS Secrets Manager Template ===")
    print(f"Secret Name: {SECRET_NAME}")
    print(f"Region: {REGION}")
    print("\nJSON Value:")
    print(json.dumps(template, indent=2))
    print("\n=== AWS CLI Command ===")
    escaped = json.dumps(template).replace('"', '\\"')
    print(f'aws secretsmanager create-secret \\')
    print(f'  --name "{SECRET_NAME}" \\')
    print(f'  --region {REGION} \\')
    print(f'  --secret-string \'{json.dumps(template)}\'')
    print()


def create_secret(region: str, profile: str = None):
    """Create the secret in AWS Secrets Manager."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("ERROR: boto3 is required. Install with: pip install boto3")
        sys.exit(1)

    session = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(region_name=region)
    client = session.client("secretsmanager")

    secret_value = generate_secret_template()

    try:
        # Check if already exists
        client.describe_secret(SecretId=SECRET_NAME)
        print(f"Secret '{SECRET_NAME}' already exists. Updating...")
        client.put_secret_value(
            SecretId=SECRET_NAME,
            SecretString=json.dumps(secret_value),
        )
        print(f"Secret '{SECRET_NAME}' updated successfully.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            # Create new
            client.create_secret(
                Name=SECRET_NAME,
                Description="Enterprise Linux Access Portal - Application Secrets",
                SecretString=json.dumps(secret_value),
                Tags=[
                    {"Key": "Application", "Value": "Linux Access Portal"},
                    {"Key": "ManagedBy", "Value": "setup_secrets.py"},
                ],
            )
            print(f"Secret '{SECRET_NAME}' created successfully in {region}.")
        else:
            print(f"ERROR: {e.response['Error']['Message']}")
            sys.exit(1)

    print("\nIMPORTANT: Update AZURE_CLIENT_SECRET and SMTP_PASSWORD in the secret:")
    print(f"  aws secretsmanager put-secret-value --secret-id {SECRET_NAME} --secret-string '<updated-json>'")
    print("\nGenerated credentials:")
    print(f"  Emergency Admin Password: {secret_value['EMERGENCY_ADMIN_PASSWORD']}")
    print("  (Save this! It won't be shown again)")


def verify_secret(region: str, profile: str = None):
    """Verify the secret exists and contains required keys."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("ERROR: boto3 is required. Install with: pip install boto3")
        sys.exit(1)

    session = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(region_name=region)
    client = session.client("secretsmanager")

    try:
        response = client.get_secret_value(SecretId=SECRET_NAME)
        secret_data = json.loads(response["SecretString"])

        required_keys = ["SECRET_KEY", "SESSION_SECRET_KEY", "ENCRYPTION_KEY", "EMERGENCY_ADMIN_PASSWORD"]
        print(f"\nSecret '{SECRET_NAME}' found in {region}")
        print(f"Keys present: {list(secret_data.keys())}")

        missing = [k for k in required_keys if k not in secret_data or not secret_data[k]]
        if missing:
            print(f"\nWARNING: Missing or empty keys: {missing}")
            sys.exit(1)
        else:
            print("\nAll required keys are present and non-empty.")
            # Check for placeholder values
            placeholders = [k for k, v in secret_data.items() if "REPLACE" in str(v)]
            if placeholders:
                print(f"WARNING: Keys still have placeholder values: {placeholders}")
            else:
                print("No placeholder values found. Ready for production.")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"ERROR: Secret '{SECRET_NAME}' not found in {region}")
            print("Run: python scripts/setup_secrets.py --create")
            sys.exit(1)
        else:
            print(f"ERROR: {e.response['Error']['Message']}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AWS Secrets Manager setup for Linux Access Portal")
    parser.add_argument("--create", action="store_true", help="Create/update secret in AWS")
    parser.add_argument("--show-template", action="store_true", help="Show the secret JSON template")
    parser.add_argument("--verify", action="store_true", help="Verify secret exists and is complete")
    parser.add_argument("--region", default=REGION, help=f"AWS region (default: {REGION})")
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    parser.add_argument("--secret-name", default=SECRET_NAME, help=f"Secret name (default: {SECRET_NAME})")

    args = parser.parse_args()

    global SECRET_NAME, REGION
    SECRET_NAME = args.secret_name
    REGION = args.region

    if args.show_template:
        show_template()
    elif args.create:
        create_secret(args.region, args.profile)
    elif args.verify:
        verify_secret(args.region, args.profile)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
