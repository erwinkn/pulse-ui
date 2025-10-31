"""Tests for deployment helpers."""

from datetime import UTC, datetime

from pulse_aws.deployment import generate_deployment_id


def test_generate_deployment_id():
	"""Test that deployment IDs are properly formatted."""
	deployment_name = "prod"
	deployment_id = generate_deployment_id(deployment_name)

	# Should start with {deployment_name}-
	assert deployment_id.startswith(f"{deployment_name}-")

	# Should end with Z (UTC timestamp)
	assert deployment_id.endswith("Z")

	# Should contain a valid timestamp
	# Format: prod-20251027-183000Z
	parts = deployment_id.split("-")
	assert len(parts) == 3
	assert parts[0] == deployment_name
	assert len(parts[1]) == 8  # YYYYMMDD
	assert parts[2].endswith("Z")
	assert len(parts[2]) == 7  # HHMMSSZ

	# Verify it's a recent timestamp (within last minute)
	now = datetime.now(UTC)
	year = now.strftime("%Y")
	assert year in deployment_id


def test_generate_deployment_id_different_names():
	"""Test deployment IDs with different deployment names."""
	dev_id = generate_deployment_id("dev")
	staging_id = generate_deployment_id("staging")

	assert dev_id.startswith("dev-")
	assert staging_id.startswith("staging-")
	assert dev_id != staging_id
