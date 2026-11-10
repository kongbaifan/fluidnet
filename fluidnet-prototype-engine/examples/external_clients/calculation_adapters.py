"""Discover and call calculations over HTTP, or use --local for in-process Python."""
from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def request_json(base_url: str, path: str, token: str, body: dict | None = None) -> dict:
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body, allow_nan=False).encode('utf-8')
    request = Request(base_url.rstrip('/') + path, data=data, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode('utf-8', errors='replace')
        raise ValueError(f'HTTP {error.code}: {detail}') from error
    except URLError as error:
        raise ValueError(f'Cannot reach FluidNet: {error.reason}') from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', help='Call the Python registry without starting an HTTP server.')
    args = parser.parse_args()
    body = {
        'adapter_id': 'hydraulics.pipe_pressure_drop',
        'version': 1,
        'request_id': str(uuid4()),
        'inputs': {'mass_flow': 1., 'density': 1000., 'viscosity': 1.,
                   'length': 10., 'diameter': 50., 'roughness': .045},
        'input_units': {'viscosity': 'mPa.s', 'diameter': 'mm', 'roughness': 'mm'},
        'output_units': {'pressure_drop': 'kPa'},
    }
    try:
        if args.local:
            from fn_engine.adapters import default_registry
            registry = default_registry()
            catalog = registry.catalog().model_dump(mode='json')
        else:
            base_url = os.environ.get('FLUIDNET_URL', 'http://127.0.0.1:8798')
            token = os.environ.get('FLUIDNET_TOKEN', '')
            catalog = request_json(base_url, '/api/v1/adapters', token)
        if not any(item['adapter_id'] == body['adapter_id'] and item['version'] == body['version']
                   for item in catalog['adapters']):
            raise ValueError('The requested pipe calculation is not registered on this FluidNet instance.')
        print(f"Discovered {len(catalog['adapters'])} adapter versions.")
        result = (registry.execute(body).model_dump(mode='json') if args.local else
                  request_json(base_url, '/api/v1/adapters/execute', token, body))
    except ValueError as error:
        print(str(error))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
