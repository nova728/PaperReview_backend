# Automatic_Review 集成使用说明

## 概述

本项目已将 `Automatic_Review` 功能集成到 `Hammer_review_backend` 中，提供了更强大的学术论文自动评审功能。

## 功能特性

### 1. 评审生成
使用 Automatic_Review 项目的原始功能生成学术论文评审：
- 基于 `prompt_generate_review_v2.txt` 模板
- 生成包含摘要、优点、缺点和决策的完整评审
- 遵循 Automatic_Review 项目的标准格式

### 2. 评审方面分类
使用 Automatic_Review 项目的方面分类功能：
- 基于 `prompt_aspect_classicification.txt` 模板
- 支持14个评审方面的自动分类
- 包括新颖性、贡献、方法、实验等各个方面

## API 接口

### 1. 自动评审接口

**端点**: `POST /api/papers/automatic-review`

**请求参数**:
```json
{
    "paper_json": {
        // 论文JSON数据，格式与原有接口相同
    },
    "temperature": 0.7,
    "max_tokens": 1024,
    "use_chunking": false,
    "include_authors": false
}
```

**响应格式**:
```json
{
    "status": "success",
    "processing_time": 5.23,
    "paper_length": 15000,
    "result": {
        "type": "automatic_review",
        "content": "评审内容...",
        "source": "Automatic_Review",
        "aspects": ["Novelty", "Contribution of the research"]
    }
}
```

### 2. 评审方面分类接口

**端点**: `POST /api/papers/review-aspects`

**请求参数**:
```json
{
    "review_text": "评审文本内容..."
}
```

**响应格式**:
```json
{
    "status": "success",
    "aspects": ["Novelty", "Contribution of the research"],
    "review_text_length": 500
}
```



## 使用方法

### 1. 启动服务

```bash
cd Hammer_review_backend
python run.py
```

### 2. 测试集成功能

```bash
python test_automatic_review_integration.py
```

### 3. 使用示例

#### Python 客户端示例

```python
import requests
import json

# 配置
base_url = "http://localhost:8080"

# 准备论文数据
paper_data = {
    "paper_json": {
        "title": "Your Paper Title",
        "abstract": [["Your abstract text..."]],
        "body": [
            {
                "section": {"index": "1", "name": "INTRODUCTION"},
                "p": [{"text": "Your paper content...", "quote": []}]
            }
        ],
        "reference": []
    }
}

# 调用自动评审接口
response = requests.post(
    f"{base_url}/api/papers/automatic-review",
    json=paper_data,
    headers={"Content-Type": "application/json"}
)

if response.status_code == 200:
    result = response.json()
    print("评审结果:", result["result"]["content"])
    print("方面分类:", result["result"]["aspects"])
else:
    print("请求失败:", response.text)
```

#### cURL 示例

```bash
# 自动评审
curl -X POST http://localhost:8080/api/papers/automatic-review \
  -H "Content-Type: application/json" \
  -d '{
    "paper_json": {
      "title": "Test Paper",
      "abstract": [["Test abstract"]],
      "body": [],
      "reference": []
    },
    "review_type": "comprehensive"
  }'

# 方面分类
curl -X POST http://localhost:8080/api/papers/review-aspects \
  -H "Content-Type: application/json" \
  -d '{"review_text": "This paper presents a novel approach..."}'


```

## 配置说明

### 1. Automatic_Review 项目路径

集成服务会自动检测 `Automatic_Review` 项目的路径：
- 默认路径: `../Automatic_Review` (相对于 `Hammer_review_backend`)
- 如果项目不存在，某些功能可能不可用

### 2. 提示词模板

集成服务会尝试加载 `Automatic_Review` 项目中的提示词模板：
- 生成模板: `Automatic_Review/generation/prompts/prompt_generate_review_v2.txt`
- 分类模板: `Automatic_Review/evaluation/prompts/prompt_aspect_classicification.txt`

### 3. LLM 服务配置

集成服务使用现有的 `VllmService` 进行LLM调用，配置在 `config/config.py` 中。

## 注意事项

1. **依赖关系**: 确保 `Automatic_Review` 项目存在且可访问
2. **LLM 服务**: 确保 vLLM 服务正常运行
3. **性能考虑**: 方面聚焦评审会调用多次LLM，处理时间较长
4. **错误处理**: 如果某个功能不可用，服务会返回相应的错误信息

## 故障排除

### 1. Automatic_Review 项目不存在

**症状**: 日志中显示 "Automatic_Review项目不存在，某些功能可能不可用"

**解决方案**: 
- 确保 `Automatic_Review` 项目在正确的位置
- 检查项目路径配置

### 2. 提示词模板加载失败

**症状**: 评审结果质量不佳或格式不正确

**解决方案**:
- 检查提示词模板文件是否存在
- 确保文件编码为 UTF-8

### 3. LLM 调用失败

**症状**: 评审生成失败或返回错误

**解决方案**:
- 检查 vLLM 服务是否正常运行
- 验证配置文件中的服务地址和端口
- 查看服务日志获取详细错误信息

## 扩展开发

### 1. 添加新的评审类型

在 `AutomaticReviewService` 中添加新的评审方法：

```python
def _generate_custom_review(self, paper_content: str) -> Dict[str, Any]:
    """生成自定义评审"""
    # 实现自定义评审逻辑
    pass
```

### 2. 添加新的评估指标

在 `evaluate_review_quality` 方法中添加新的评估维度：

```python
def evaluate_review_quality(self, review_text: str, reference_review: str = None) -> Dict[str, float]:
    # 添加新的评估指标
    scores = {
        "overall_score": 0.75,
        "completeness": 0.8,
        "objectivity": 0.7,
        "constructiveness": 0.8,
        "new_metric": 0.85  # 新指标
    }
    return scores
```

### 3. 集成更多 Automatic_Review 功能

可以进一步集成 `Automatic_Review` 项目中的其他功能，如：
- 训练数据管理
- 模型微调
- 评估脚本
- 数据预处理

## 更新日志

- **v1.0.0**: 初始集成版本，支持基本的结构化评审、方面分类和质量评估功能 