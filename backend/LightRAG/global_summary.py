# global_summary.py
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# ====== 配置区（与你的 abstract.py 一致）======
API_KEY = "sk-755bc40bad1f473eacc1a2b24b758573"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-long"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def split_text_by_chars(text: str, chunk_size: int = 200) -> list[str]:
    """按字符切分，每片约 200 字"""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def summarize_chunk(chunk: str, idx: int, total: int) -> str:
    """对单个 200 字片段生成一句话摘要"""
    prompt = f"请用一句话（不超过 30 字）概括以下内容的核心：\n\n{chunk}"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=64
        )
        summary = response.choices[0].message.content.strip()
        print(f"[{idx + 1}/{total}] 小摘要: {summary}")
        return summary
    except Exception as e:
        print(f"[{idx + 1}/{total}] 失败: {e}")
        return ""


def generate_global_summary(full_text: str) -> str:
    """主函数：200字切片 → 小摘要 → 全局摘要"""
    print("🔍 开始生成全局摘要（Mindscape）...")

    # Step 1: 切片（200字/片）
    chunks = split_text_by_chars(full_text, chunk_size=200)
    print(f"📄 文本共 {len(full_text)} 字，切分为 {len(chunks)} 片")

    # Step 2: 并发生成小摘要
    small_summaries = []
    with ThreadPoolExecutor(max_workers=3) as executor:  # 控制并发防限流
        future_to_idx = {
            executor.submit(summarize_chunk, chunk, i, len(chunks)): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            try:
                res = future.result()
                if res:
                    small_summaries.append(res)
            except:
                pass

    if not small_summaries:
        raise RuntimeError("所有小摘要生成失败")

    # Step 3: 拼接小摘要，生成全局摘要
    combined = "\n".join(small_summaries)
    final_prompt = (
            "以下是文章各片段的摘要，请融合成一段连贯、精炼的全局摘要（200字以内），"
            "突出核心事件、人物和主旨，不要分点，直接输出摘要：\n\n" + combined
    )

    print("\n🧠 正在生成最终全局摘要（Mindscape）...")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": final_prompt}],
            temperature=0.5,
            max_tokens=256
        )
        mindscape = response.choices[0].message.content.strip()
        print("✅ 全局摘要生成成功！")
        return mindscape
    except Exception as e:
        raise RuntimeError(f"全局摘要生成失败: {e}")


# ====== 示例用法 ======
if __name__ == "__main__":
    # 测试：读取文件
    test_file = "book.txt"
    if not os.path.exists(test_file):
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("这是一个很长很长的测试文本..." * 100)

    with open(test_file, "r", encoding="utf-8") as f:
        text = f.read()

    summary = generate_global_summary(text)
    print("\n" + "=" * 50)
    print("【Mindscape 全局摘要】")
    print(summary)
    print("=" * 50)