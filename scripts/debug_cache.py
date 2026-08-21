import json

CACHE = "/root/autodl-tmp/pythonproject3_mia/mia_rag_storage/user_1/kv_store_llm_response_cache.json"

with open(CACHE) as f:
    data = json.load(f)

for i, (k, v) in enumerate(data.items()):
    if i >= 3:
        break
    print("=== KEY:", k[:60])
    ret = v.get("return", "") if isinstance(v, dict) else str(v)
    print(ret[:800])
    print()
