import os
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv()

class EmailClassification(BaseModel):
    """邮件分类结果"""
    category: str = Field(description="邮件分类：spam(垃圾邮件), important(重要通知), normal(正常交流)")
    confidence: float = Field(description="分类置信度，0-1之间")
    reason: str = Field(description="分类理由")
    priority: Optional[int] = Field(description="重要通知的优先级，1-5，5最高")
    summary: Optional[str] = Field(description="邮件内容摘要（仅重要邮件需要）")

class EmailClassifier:
    def __init__(self):
        self.llm = ChatOpenAI(
            temperature=0,
            model_name="gpt-3.5-turbo",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
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
    def __init__(self):
        self.llm = ChatOpenAI(
            temperature=0.3,
            model_name="gpt-3.5-turbo",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
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