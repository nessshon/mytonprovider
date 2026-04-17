from __future__ import annotations

import requests

from .models import BagDetails, BagsListResponse, OkResponse

_DEFAULT_TIMEOUT = 5.0
_VERIFY_TIMEOUT = 60.0


class StorageApi:
    """HTTP client for the tonutils-storage control API.

    See https://github.com/xssnick/tonutils-storage#http-api for endpoint docs.
    """

    def __init__(self, host: str, port: int, *, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout

    def list_bags(self) -> BagsListResponse:
        response = requests.get(f"{self._base_url}/api/v1/list", timeout=self._timeout)
        response.raise_for_status()
        return BagsListResponse.model_validate(response.json())

    def get_bag(self, bag_id: str) -> BagDetails:
        response = requests.get(
            f"{self._base_url}/api/v1/details",
            params={"bag_id": bag_id},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return BagDetails.model_validate(response.json())

    def add_bag(
        self,
        bag_id: str,
        *,
        path: str,
        files: list[int] | None = None,
        download_all: bool = True,
    ) -> None:
        payload: dict[str, object] = {
            "bag_id": bag_id,
            "path": path,
            "download_all": download_all,
        }
        if files is not None:
            payload["files"] = files
        response = requests.post(
            f"{self._base_url}/api/v1/add",
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

    def remove_bag(self, bag_id: str, *, with_files: bool = False) -> None:
        response = requests.post(
            f"{self._base_url}/api/v1/remove",
            json={"bag_id": bag_id, "with_files": with_files},
            timeout=self._timeout,
        )
        response.raise_for_status()

    def verify_bag(self, bag_id: str, *, only_files_existence: bool = False) -> bool:
        response = requests.post(
            f"{self._base_url}/api/v1/verify",
            json={"bag_id": bag_id, "only_files_existence": only_files_existence},
            timeout=_VERIFY_TIMEOUT,
        )
        response.raise_for_status()
        return OkResponse.model_validate(response.json()).ok

    def set_verbosity(self, verbosity: int) -> None:
        response = requests.post(
            f"{self._base_url}/api/v1/logger",
            json={"verbosity": verbosity},
            timeout=self._timeout,
        )
        response.raise_for_status()
