#!/usr/bin/env python3
"""Test script for ensure_acm_certificate."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

# Add src to path so we can import pulse_aws
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pulse_aws.certificate import ensure_acm_certificate


def check_dns_record(name: str, record_type: str = "CNAME") -> bool:
	"""Check if a DNS record is resolvable."""
	try:
		result = subprocess.run(
			["dig", name, record_type, "+short"],
			capture_output=True,
			text=True,
			check=True,
		)

		if result.stdout.strip():
			print(f"  ✅ {name} → {result.stdout.strip()}")
			return True
		else:
			print(f"  ❌ {name} not found")
			return False

	except subprocess.CalledProcessError as e:
		print(f"  ❌ Error checking {name}: {e}")
		return False
	except FileNotFoundError:
		print("  ❌ 'dig' command not found. Install it with: brew install bind")
		return False


async def main() -> None:
	"""Test certificate creation for test.stoneware.rocks."""
	domain = "test.stoneware.rocks"

	print(f"🔍 Requesting ACM certificate for: {domain}")

	# Create certificate without waiting
	cert = await ensure_acm_certificate(domain)

	print(f"📋 Certificate status: {cert.status}")
	print()

	# Check DNS resolution
	if cert.dns_configuration and cert.dns_configuration.records:
		print("🔍 Checking DNS resolution:")
		all_resolved = True
		for record in cert.dns_configuration.records:
			resolved = check_dns_record(record.name, record.type)
			if not resolved:
				all_resolved = False

		print()
		if all_resolved:
			print("✅ All DNS records are configured correctly!")
		else:
			print(
				"⚠️  Some DNS records are not present yet. If you already configured them, wait a few minutes and re-run this script to check again."
			)


if __name__ == "__main__":
	asyncio.run(main())
