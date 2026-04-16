#!/usr/bin/env python3
"""诊断 Anthropic SDK 客户端结构"""

import os
import sys

# 添加项目路径
sys.path.insert(0, r'd:\kunming')

# 设置测试密钥
os.environ["ANTHROPIC_API_KEY"] = "test-key"

try:
    from agent.anthropic_adapter import build_anthropic_client

    client = build_anthropic_client("test-key", None)

    print("=== Anthropic Client Structure ===")
    print(f"Client type: {type(client)}")
    print(f"Client module: {type(client).__module__}")

    # 检查 _client 属性
    http_client = getattr(client, "_client", None)
    print(f"\n_client attribute: {http_client}")
    if http_client:
        print(f"  Type: {type(http_client)}")
        print(f"  Module: {type(http_client).__module__}")

        # 检查 _transport
        transport = getattr(http_client, "_transport", None)
        print(f"\n  _transport: {transport}")
        if transport:
            print(f"    Type: {type(transport)}")

            # 检查 _pool
            pool = getattr(transport, "_pool", None)
            print(f"\n    _pool: {pool}")
            if pool:
                print(f"      Type: {type(pool)}")

    # 列出所有属性
    print("\n=== All attributes containing 'client' or 'http' ===")
    for attr in dir(client):
        if 'client' in attr.lower() or 'http' in attr.lower():
            val = getattr(client, attr, None)
            print(f"  {attr}: {type(val).__name__}")

    print("\n=== All attributes containing 'transport' or 'pool' ===")
    for attr in dir(client):
        if 'transport' in attr.lower() or 'pool' in attr.lower():
            val = getattr(client, attr, None)
            print(f"  {attr}: {type(val).__name__}")

    # 检查是否有 _requester 或其他内部属性
    print("\n=== Checking _requester or _http ===")
    for attr in ['_requester', '_http', '_session', '_connection']:
        val = getattr(client, attr, None)
        if val is not None:
            print(f"  {attr}: {type(val)}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
