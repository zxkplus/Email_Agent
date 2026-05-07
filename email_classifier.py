import os
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

load_dotenv()

# 支持的模型提供商配置
MODEL_PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-3.5-turbo",
        "api_key_env": "OPENAI_API_KEY"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY"
    },
    "azure": {
        "base_url": "https://your-resource.openai.azure.com/",
        "default_model": "gpt-35-turbo",
        "api_key_env": "AZURE_OPENAI_API_KEY"
    },
    "zhipu": {  # 智谱AI
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4",
        "api_key_env": "ZHIPU_API_KEY"
    },
    "qwen": {  # 通义千问
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY"
    },
    "moonshot": {  # 月之暗面
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "api_key_env": "MOONSHOT_API_KEY"
    },
    "ollama": {  # 本地 Ollama
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen:7b",
        "api_key_env": "OLLAMA_API_KEY"  # 可以随便填，Ollama不需要真的key
    }
}

class EmailClassification(BaseModel):
    """邮件分类结果"""
    category: str = Field(description="邮件分类：spam(垃圾邮件), important(重要通知), normal(正常交流)")
    confidence: float = Field(description="分类置信度，0-1之间")
    reason: str = Field(description="分类理由")
    priority: Optional[int] = Field(description="重要通知的优先级，1-5，5最高")
    summary: Optional[str] = Field(description="邮件内容摘要（仅重要邮件需要）")

class LLMFactory:
    """LLM 工厂类，用于创建不同提供商的 LLM 实例"""
    
    @staticmethod
    def create_llm(provider: str = None, model: str = None, **kwargs) -> ChatOpenAI:
        """
        创建 LLM 实例
        
        Args:
            provider: 模型提供商 (openai/deepseek/azure/zhipu/qwen/moonshot/ollama)
            model: 具体模型名称，不填则使用默认
            **kwargs: 其他参数传递给 ChatOpenAI
        """
        # 如果没指定 provider，从环境变量读取
        if provider is None:
            provider = os.getenv("LLM_PROVIDER", "openai").lower()
        
        if provider not in MODEL_PROVIDERS:
            raise ValueError(f"不支持的模型提供商: {provider}。支持的提供商: {list(MODEL_PROVIDERS.keys())}")
        
        config = MODEL_PROVIDERS[provider]
        api_key = os.getenv(config["api_key_env"], "")
        
        # 如果没指定 model，使用默认
        if model is None:
            model = os.getenv(f"{provider.upper()}_MODEL", config["default_model"])
        
        # 构建 LLM 配置
        llm_kwargs = {
            "temperature": kwargs.get("temperature", 0),
            "model_name": model,
            "openai_api_key": api_key,
            "openai_api_base": config["base_url"],
        }
        
        # Azure 特殊配置
        if provider == "azure":
            llm_kwargs["model_kwargs"] = {"engine": model}
        
        # 支持传入的额外参数
        llm_kwargs.update(kwargs)
        
        return ChatOpenAI(**llm_kwargs)

class EmailClassifier:
    def __init__(self, provider: str = None, model: str = None):
        """
        邮件分类器
        
        Args:
            provider: 模型提供商，不填则从环境变量 LLM_PROVIDER 读取
            model: 模型名称，不填则使用提供商默认
        """
        # 创建 LLM 实例
        self.llm = LLMFactory.create_llm(provider=provider, model=model, temperature=0)
        self.parser = PydanticOutputParser(pydantic_object=EmailClassification)
        
        self.prompt = ChatPromptTemplate.from_template("""
你是一个专业的邮件分类助手。请根据邮件内容进行分类。

分类标准：
1. spam（垃圾邮件）：促销广告、钓鱼链接、中奖通知、不明来源推广、诱导点击、大量emoji营销
2. important（重要通知）：账单、验证码、系统通知、会议邀请、付款确认、密码重置、紧急事务
3. normal（正常交流）：同事沟通、客户邮件、朋友来信、回复邮件

邮件信息：
发件人: {sender}
主题: {subject}
内容摘要: {body}

{format_instructions}

请仔细分析并输出分类结果。
""")
    
    def classify(self, email_data):
        """分类单封邮件"""
        prompt_input = self.prompt.format_prompt(
            sender=email_data['sender'],
            subject=email_data['subject'],
            body=email_data['body'],
            format_instructions=self.parser.get_format_instructions()
        )
        
        output = self.llm(prompt_input.to_messages())
        
        try:
            result = self.parser.parse(output.content)
            return result
        except Exception as e:
            print(f"解析分类结果失败: {e}")
            print(f"原始输出: {output.content}")
            # 返回默认分类
            return EmailClassification(
                category="normal",
                confidence=0.5,
                reason="分类解析失败，默认归为正常邮件"
            )

class EmailSummarizer:
    """重要邮件摘要生成器"""
    def __init__(self, provider: str = None, model: str = None):
        self.llm = LLMFactory.create_llm(provider=provider, model=model, temperature=0.3)
        
        self.prompt = ChatPromptTemplate.from_template("""
请为以下重要邮件生成一个简洁的摘要，突出关键信息和行动项。

发件人: {sender}
主题: {subject}
内容: {body}

请用1-2句话概括邮件的核心内容，如果有需要处理的事项请明确指出。
""")
    
    def summarize(self, email_data):
        prompt_input = self.prompt.format_prompt(
            sender=email_data['sender'],
            subject=email_data['subject'],
            body=email_data['body']
        )
        
        output = self.llm(prompt_input.to_messages())
        return output.content