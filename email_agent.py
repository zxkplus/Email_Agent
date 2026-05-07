import os
import json
from datetime import datetime
from dotenv import load_dotenv
from gmail_client import GmailClient
from email_classifier import EmailClassifier, EmailSummarizer

load_dotenv()

class EmailAgent:
    def __init__(self):
        self.gmail = GmailClient()
        self.classifier = EmailClassifier()
        self.summarizer = EmailSummarizer()
        self.stats = {
            'total': 0,
            'spam': 0,
            'important': 0,
            'normal': 0
        }
        self.important_emails_summary = []
        
    def process_emails(self, max_emails=20):
        """处理邮件"""
        print("=" * 60)
        print(f"📧 邮件整理Agent 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 获取未读邮件
        print(f"\n🔍 正在获取未读邮件...")
        emails = self.gmail.get_unread_emails(max_emails)
        
        if not emails:
            print("✅ 没有未读邮件需要处理")
            return
        
        print(f"📬 共获取到 {len(emails)} 封未读邮件\n")
        
        # 处理每封邮件
        for i, email in enumerate(emails, 1):
            print(f"[{i}/{len(emails)}] 处理邮件:")
            print(f"    发件人: {email['sender'][:60]}...")
            print(f"    主题: {email['subject'][:60]}...")
            
            # AI 分类
            classification = self.classifier.classify(email)
            print(f"    分类结果: {classification.category} (置信度: {classification.confidence:.2f})")
            print(f"    分类理由: {classification.reason}")
            
            # 执行对应操作
            self._process_classification(email, classification)
            
            self.stats['total'] += 1
            print()
        
        # 生成报告
        self._generate_report()
    
    def _process_classification(self, email, classification):
        """根据分类执行操作"""
        msg_id = email['id']
        
        if classification.category == "spam":
            # 标记为垃圾邮件
            if classification.confidence > 0.8:  # 高置信度才自动标记
                self.gmail.mark_as_spam(msg_id)
                print("    ✅ 已自动标记为垃圾邮件")
            else:
                self.gmail.apply_label(msg_id, "🤔疑似垃圾")
                print("    ⚠️ 置信度较低，已标记为【疑似垃圾】待人工确认")
            self.stats['spam'] += 1
            
        elif classification.category == "important":
            # 重要邮件处理
            self.gmail.apply_label(msg_id, "⭐重要通知")
            self.gmail.apply_label(msg_id, "📌待处理")  # 保留待处理标签
            
            # 生成摘要
            summary = self.summarizer.summarize(email)
            self.important_emails_summary.append({
                'subject': email['subject'],
                'sender': email['sender'],
                'priority': classification.priority or 3,
                'summary': summary
            })
            
            print(f"    ⭐ 已标记为【重要通知】，优先级: {classification.priority or 3}/5")
            print(f"    📝 摘要: {summary}")
            self.stats['important'] += 1
            
        else:  # normal
            # 正常邮件按发件人归档
            # 提取发件人名称
            sender_name = email['sender'].split('<')[0].strip()
            if len(sender_name) > 30:
                sender_name = sender_name[:30]
            
            label_name = f"👥交流/{sender_name}"
            self.gmail.apply_label(msg_id, label_name)
            print(f"    ✅ 已归档到【{label_name}】")
            self.stats['normal'] += 1
        
        # 标记为已读
        self.gmail.mark_as_read(msg_id)
    
    def _generate_report(self):
        """生成处理报告"""
        print("=" * 60)
        print("📊 处理报告")
        print("=" * 60)
        print(f"总计处理邮件: {self.stats['total']} 封")
        print(f"  🟢 正常交流: {self.stats['normal']} 封")
        print(f"  🟡 重要通知: {self.stats['important']} 封")
        print(f"  🔴 垃圾邮件: {self.stats['spam']} 封")
        
        if self.important_emails_summary:
            print("\n" + "=" * 60)
            print("⭐ 重要邮件摘要")
            print("=" * 60)
            
            # 按优先级排序
            self.important_emails_summary.sort(key=lambda x: x['priority'], reverse=True)
            
            for i, email in enumerate(self.important_emails_summary, 1):
                print(f"\n[{i}] 优先级 {'★' * email['priority']}")
                print(f"    主题: {email['subject']}")
                print(f"    发件人: {email['sender']}")
                print(f"    摘要: {email['summary']}")
        
        # 保存报告到文件
        report = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'important_emails': self.important_emails_summary
        }
        
        with open('email_processing_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 详细报告已保存到: email_processing_report.json")

def main():
    agent = EmailAgent()
    agent.process_emails(max_emails=20)

if __name__ == "__main__":
    main()