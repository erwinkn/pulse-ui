from __future__ import annotations

from pulse_railway.images import (
	OFFICIAL_JANITOR_IMAGE_REPOSITORY,
	OFFICIAL_ROUTER_IMAGE_REPOSITORY,
	official_janitor_image_ref,
	official_router_image_ref,
)


def test_official_runtime_images_use_published_tag() -> None:
	assert official_router_image_ref() == (f"{OFFICIAL_ROUTER_IMAGE_REPOSITORY}:0.3.5")
	assert official_janitor_image_ref() == (
		f"{OFFICIAL_JANITOR_IMAGE_REPOSITORY}:0.3.5"
	)


def test_official_runtime_images_accept_explicit_version() -> None:
	assert official_router_image_ref(version="1.2.3") == (
		f"{OFFICIAL_ROUTER_IMAGE_REPOSITORY}:1.2.3"
	)
	assert official_janitor_image_ref(version="1.2.3") == (
		f"{OFFICIAL_JANITOR_IMAGE_REPOSITORY}:1.2.3"
	)
