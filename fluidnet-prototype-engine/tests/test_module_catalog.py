"""M3 模块目录契约：8 个倍思鹿参考模块必须由后端自动发现并出现在 /api/v1/modules。

测试只依赖 HTTP 响应，不依赖模块顺序；每个用例使用独立的空模块存储目录，
既不读取开发机上 `.runtime` 里已保存的版本，也不向用户目录写入任何文件。
"""

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app

REFERENCE_MODULE_IDS = (
    'pipe_fitting',
    'check_valve',
    'fan_coil_unit',
    'cooling_tower',
    'fan',
    'pump_variable_speed',
    'capillary_tube',
    'valve_equal_percentage',
)


@pytest.fixture()
def client(tmp_path):
    # 临时模块存储目录为空：目录只来自 modules/ 种子包，重复运行结果一致。
    with TestClient(create_app(module_storage_root=tmp_path)) as test_client:
        yield test_client


def module_catalog(client):
    response = client.get('/api/v1/modules')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload.get('modules'), list)
    return payload['modules']


def module_map(client):
    modules = module_catalog(client)
    ids = [module['id'] for module in modules]
    assert len(ids) == len(set(ids)), f'模块目录返回了重复 id：{ids}'
    return {module['id']: module for module in modules}


def test_catalog_lists_all_reference_modules(client):
    modules = module_map(client)
    missing = [module_id for module_id in REFERENCE_MODULE_IDS if module_id not in modules]
    assert not missing, f'/api/v1/modules 缺少参考模块：{missing}'


@pytest.mark.parametrize('module_id', REFERENCE_MODULE_IDS)
def test_reference_module_contract(client, module_id):
    module = module_map(client)[module_id]
    assert module['name'], f'{module_id} 缺少中文名称'
    assert module['description'], f'{module_id} 缺少说明文字'
    assert module['category'] == '倍思鹿参考模块'
    assert module['runtime'] == 'python'
    assert module['version'] == 1

    ports = module['ports']
    assert len(ports) >= 2, f'{module_id} 至少应有 2 个端口'
    assert {port['domain'] for port in ports} == {'fluid'}, f'{module_id} 端口领域应全为 fluid'
    directions = {port['direction'] for port in ports}
    assert directions <= {'in', 'out'}, f'{module_id} 端口方向只能是 in/out：{directions}'
    assert {'in', 'out'} <= directions, f'{module_id} 应同时提供入口和出口：{directions}'

    channels = module['channels']
    assert len(channels) >= 1, f'{module_id} 至少应有 1 条通路'
    port_ids = {port['id'] for port in ports}
    for channel in channels:
        assert channel['input_port'] in port_ids, f'{module_id} 通路入口未绑定已有端口'
        assert channel['output_port'] in port_ids, f'{module_id} 通路出口未绑定已有端口'
        assert channel['input_port'] != channel['output_port'], f'{module_id} 通路两端不能是同一端口'
    assert any(channel.get('enabled', True) for channel in channels), f'{module_id} 至少应有 1 条启用通路'

    assert len(module['parameters']) > 0, f'{module_id} 参数数量应大于 0'
    assert len(module['variables']) > 0, f'{module_id} variables 不能为空'

    content_hash = module.get('content_hash')
    definition_hash = module.get('definition_hash')
    assert isinstance(content_hash, str) and len(content_hash) == 64, f'{module_id} content_hash 应为 64 位哈希'
    assert isinstance(definition_hash, str) and len(definition_hash) == 64, f'{module_id} definition_hash 应为 64 位哈希'

    package = module.get('package')
    assert package is not None, f'{module_id} Python 包应返回 package 绑定'
    assert package['module_id'] == module_id
    assert package['version'] == '1.0.0'
    assert package['content_hash'] == content_hash
    assert package['definition_hash'] == definition_hash


def test_health_reports_module_versions_capability(client):
    response = client.get('/api/v1/health')
    assert response.status_code == 200, response.text
    capabilities = response.json()['capabilities']
    assert capabilities['module_versions'] is True
