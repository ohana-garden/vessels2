"""
A0 Framework - API Handler Base Class

Base class for all API endpoints with guardian integration and extension hooks.
Follows A0 patterns for consistent request/response processing.

Usage:
    class MyEndpoint(ApiHandler):
        async def process(self, input: Input, request: Request) -> Output:
            # input is already sanitized by guardians
            return {"result": "ok"}
"""

from abc import abstractmethod
import json
import threading
from typing import Union, TypedDict, Dict, Any, Optional
from attr import dataclass
from flask import Request, Response, jsonify, Flask, session, request, send_file
from agent import AgentContext
from initialize import initialize_agent
from python.helpers.print_style import PrintStyle
from python.helpers.errors import format_error
from python.helpers.guardians import guard_input, GuardianType, guard
from werkzeug.serving import make_server

Input = dict
Output = Union[Dict[str, Any], Response, TypedDict]  # type: ignore


class ApiHandler:
    def __init__(self, app: Flask, thread_lock: threading.Lock):
        self.app = app
        self.thread_lock = thread_lock

    @classmethod
    def requires_loopback(cls) -> bool:
        return False

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return cls.requires_auth()

    @classmethod
    def use_guardians(cls) -> bool:
        """Override to disable guardian sanitization for specific endpoints."""
        return True

    @abstractmethod
    async def process(self, input: Input, request: Request) -> Output:
        pass

    async def before_process(self, input: Input, request: Request) -> Input:
        """
        Hook called before process(). Override for custom pre-processing.
        Can modify input data before it reaches process().
        """
        return input

    async def after_process(self, output: Output, request: Request) -> Output:
        """
        Hook called after process(). Override for custom post-processing.
        Can modify output data before it's returned.
        """
        return output

    def _sanitize_input(self, input_data: Input, source: str = "api") -> Input:
        """
        Sanitize input data through guardians.
        Recursively sanitizes all string values in the input dict.
        """
        if not self.use_guardians():
            return input_data

        return self._sanitize_dict(input_data, source)

    def _sanitize_dict(self, data: dict, source: str) -> dict:
        """Recursively sanitize dictionary values."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = guard_input(value, source=f"{source}.{key}")
            elif isinstance(value, dict):
                result[key] = self._sanitize_dict(value, source)
            elif isinstance(value, list):
                result[key] = self._sanitize_list(value, source)
            else:
                result[key] = value
        return result

    def _sanitize_list(self, data: list, source: str) -> list:
        """Recursively sanitize list items."""
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(guard_input(item, source=source))
            elif isinstance(item, dict):
                result.append(self._sanitize_dict(item, source))
            elif isinstance(item, list):
                result.append(self._sanitize_list(item, source))
            else:
                result.append(item)
        return result

    async def handle_request(self, request: Request) -> Response:
        try:
            # Parse input data from request
            input_data: Input = {}
            if request.is_json:
                try:
                    if request.data:
                        input_data = request.get_json()
                except Exception as e:
                    PrintStyle().print(f"Error parsing JSON: {str(e)}")
                    input_data = {}

            # Sanitize input through guardians
            endpoint_name = self.__class__.__name__
            input_data = self._sanitize_input(input_data, source=f"api.{endpoint_name}")

            # Call before_process hook
            input_data = await self.before_process(input_data, request)

            # Process via handler
            output = await self.process(input_data, request)

            # Call after_process hook
            output = await self.after_process(output, request)

            # Return output based on type
            if isinstance(output, Response):
                return output
            else:
                response_json = json.dumps(output)
                return Response(
                    response=response_json, status=200, mimetype="application/json"
                )

        except Exception as e:
            error = format_error(e)
            PrintStyle.error(f"API error: {error}")
            return Response(response=error, status=500, mimetype="text/plain")

    # get context to run agent zero in
    def use_context(self, ctxid: str, create_if_not_exists: bool = True):
        with self.thread_lock:
            if not ctxid:
                first = AgentContext.first()
                if first:
                    AgentContext.use(first.id)
                    return first
                context = AgentContext(config=initialize_agent(), set_current=True)
                return context
            got = AgentContext.use(ctxid)
            if got:
                return got
            if create_if_not_exists:
                context = AgentContext(config=initialize_agent(), id=ctxid, set_current=True)
                return context
            else:
                raise Exception(f"Context {ctxid} not found")
            
