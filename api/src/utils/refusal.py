"""What a crud module raises when its rules refuse a change, and the route class that answers it over HTTP.

crud/ knows the rules, not HTTP: it raises `Refused(status, Spanish detail)`. A router whose crud raises it is
built with `route_class=RefusedRoute`, which answers it as the HTTPException it names, wherever the router is
mounted (the app, or a test that mounts the routers alone).
"""
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute


class Refused(Exception):
    """A change the rules do not allow: answered as HTTP `status_code` with `detail`."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class RefusedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def answered(request: Request):
            try:
                return await handler(request)
            except Refused as refused:
                raise HTTPException(status_code=refused.status_code, detail=refused.detail) from refused

        return answered
