#!/usr/bin/env python3
"""
政策关键词搜索辅助脚本
用于快速在政策文本中提取关键词频率和上下文
"""

import re
from collections import Counter

def extract_keywords(text, keyword_list):
    """
    在政策文本中搜索三类关键词并统计频率
    """
    results = {"定调词": {}, "动词": {}, "程度词": {}}
    for category, keywords in keyword_list.items():
        for kw in keywords:
            count = len(re.findall(rf'\b{kw}\b', text, re.IGNORECASE))
            if count > 0:
                results[category][kw] = count
    return results

def compare_policies(text1, text2, keyword_list):
    """
    比较两份政策文本的关键词频率差异
    """
    res1 = extract_keywords(text1, keyword_list)
    res2 = extract_keywords(text2, keyword_list)
    diff = {}
    for cat in res1:
        diff[cat] = {}
        all_kw = set(res1[cat].keys()) | set(res2[cat].keys())
        for kw in all_kw:
            delta = res2[cat].get(kw, 0) - res1[cat].get(kw, 0)
            diff[cat][kw] = delta
    return diff

# 使用示例
if __name__ == "__main__":
    sample_keywords = {
        "定调词": ["着力", "大力", "坚决", "全力"],
        "动词": ["推动", "鼓励", "支持", "限制", "严控"],
        "程度词": ["稳步", "加速", "有序", "逐步"]
    }
    # 示例文本
    text_2023 = "推动算力基础设施建设，稳步推进东数西算"
    text_2025 = "着力解决算力互联互通问题，加速构建全国算力网"
    diff = compare_policies(text_2023, text_2025, sample_keywords)
    print("关键词变化:", diff)