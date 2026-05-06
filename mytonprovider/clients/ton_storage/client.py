from typing import Any

import requests

from .models import BagDetails, BagsListResponse, OkResponse


class StorageApi:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        request_timeout: float = 5.0,
        verify_timeout: float = 60.0,
    ) -> None:
        self._base_url = f"http://{host}:{port}"
        self._request_timeout = request_timeout
        self._verify_timeout = verify_timeout

    def list_bags(self) -> BagsListResponse:
        return BagsListResponse.model_validate(self._get("/api/v1/list"))

    def get_bag(self, bag_id: str) -> BagDetails:
        return BagDetails.model_validate(self._get("/api/v1/details", params={"bag_id": bag_id}))

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
        self._post("/api/v1/add", payload)

    def stop_bag(self, bag_id: str) -> None:
        self._post("/api/v1/stop", {"bag_id": bag_id})

    def remove_bag(self, bag_id: str, *, with_files: bool = False) -> None:
        self._post("/api/v1/remove", {"bag_id": bag_id, "with_files": with_files})

    def verify_bag(self, bag_id: str, *, only_files_existence: bool = False) -> bool:
        data = self._post(
            "/api/v1/verify",
            {"bag_id": bag_id, "only_files_existence": only_files_existence},
            timeout=self._verify_timeout,
        )
        return OkResponse.model_validate(data).ok

    def set_verbosity(self, verbosity: int) -> None:
        self._post("/api/v1/logger", {"verbosity": verbosity})

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = requests.get(f"{self._base_url}{path}", params=params, timeout=self._request_timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any], *, timeout: float | None = None) -> Any:
        response = requests.post(
            f"{self._base_url}{path}",
            json=payload,
            timeout=timeout if timeout is not None else self._request_timeout,
        )
        response.raise_for_status()
        return response.json() if response.content else None
