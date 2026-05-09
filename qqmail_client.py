import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
import re
import html2text

class QQMailClient:
    def __init__(self, email_address=None, auth_code=None):
        """
        QQ邮箱客户端
        
        Args:
            email_address: QQ邮箱地址（如 123456@qq.com）
            auth_code: QQ邮箱授权码（不是密码）
        """
        # 从环境变量读取配置
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        self.email_address = email_address or os.getenv("QQMAIL_ADDRESS")
        self.auth_code = auth_code or os.getenv("QQMAIL_AUTH_CODE")
        
        # QQ邮箱服务器配置
        self.imap_server = "imap.qq.com"
        self.imap_port = 993
        self.smtp_server = "smtp.qq.com"
        self.smtp_port = 465
        
        # 标签映射（因为QQ邮箱用文件夹而不是标签）
        self.label_folders = {
            "⭐重要通知": "重要通知",
            "📌待处理": "待处理",
            "🤔疑似垃圾": "疑似垃圾",
            "👥交流": "交流"
        }
        
        self.imap = None
        self._connect_imap()
        self._create_folders()
    
    def _connect_imap(self):
        """连接 IMAP 服务器"""
        self.imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
        self.imap.login(self.email_address, self.auth_code)
    
    def _create_folders(self):
        """创建必要的文件夹"""
        for folder_name in self.label_folders.values():
            try:
                self.imap.create(folder_name)
            except:
                pass
    
    def _encode_folder_name(self, folder_name):
        """将文件夹名称编码为IMAP兼容的UTF-7格式"""
        if isinstance(folder_name, str):
            # IMAP要求使用修改版UTF-7编码
            return folder_name.encode('utf-7').decode('ascii')
        return folder_name
    
    def _decode_folder_name(self, encoded_folder_name):
        """将IMAP UTF-7编码的文件夹名称解码回UTF-8"""
        if isinstance(encoded_folder_name, str):
            try:
                return encoded_folder_name.encode('ascii').decode('utf-7')
            except:
                return encoded_folder_name
        return encoded_folder_name
    
    def get_unread_emails(self, max_results=50):
        """获取未读邮件"""
        emails = []
        try:
            # 选择收件箱
            self.imap.select('INBOX')
            
            # 搜索未读邮件
            status, messages = self.imap.search(None, 'UNSEEN')
            if status != 'OK':
                return emails
            
            # 获取邮件ID列表
            msg_ids = messages[0].split()
            if not msg_ids:
                return emails
            
            # 只处理前max_results封邮件
            msg_ids = msg_ids[-max_results:] if len(msg_ids) > max_results else msg_ids
            
            for msg_id in msg_ids:
                email_data = self._get_email_detail(msg_id.decode())
                if email_data:
                    emails.append(email_data)
                    
        except Exception as e:
            print(f"获取未读邮件失败: {e}")
            
        return emails
    
    def _get_email_detail(self, msg_id):
        """获取邮件详情"""
        try:
            # 获取邮件数据
            status, msg_data = self.imap.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                return None
                
            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            # 解码主题
            subject = self._decode_mime_words(email_message.get('Subject', ''))
            sender = self._decode_mime_words(email_message.get('From', ''))
            date = email_message.get('Date', '')
            
            # 提取邮件正文
            body = self._extract_email_body(email_message)
            
            return {
                'msg_id': msg_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body[:2000],  # 限制长度
                'snippet': body[:100] if body else ''
            }
        except Exception as e:
            print(f"获取邮件详情失败: {e}")
            return None
    
    def _decode_mime_words(self, s):
        """解码MIME编码的字符串"""
        if s is None:
            return ""
        decoded_parts = decode_header(s)
        decoded_string = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    decoded_string += part.decode(encoding, errors='ignore')
                else:
                    decoded_string += part.decode('utf-8', errors='ignore')
            else:
                decoded_string += part
        return decoded_string
    
    def _extract_email_body(self, email_message):
        """提取邮件正文"""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                    
                if content_type == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    body += part.get_payload(decode=True).decode(charset, errors='ignore')
                elif content_type == "text/html":
                    charset = part.get_content_charset() or 'utf-8'
                    html_content = part.get_payload(decode=True).decode(charset, errors='ignore')
                    # 转换HTML为纯文本
                    h = html2text.HTML2Text()
                    h.ignore_links = True
                    h.ignore_images = True
                    body += h.handle(html_content)
        else:
            content_type = email_message.get_content_type()
            charset = email_message.get_content_charset() or 'utf-8'
            payload = email_message.get_payload(decode=True)
            if payload:
                if content_type == "text/html":
                    html_content = payload.decode(charset, errors='ignore')
                    h = html2text.HTML2Text()
                    h.ignore_links = True
                    h.ignore_images = True
                    body = h.handle(html_content)
                else:
                    body = payload.decode(charset, errors='ignore')
        
        return body.strip()
    
    def move_to_folder(self, msg_id, folder_name):
        """移动邮件到指定文件夹"""
        # 对文件夹名称进行UTF-7编码
        encoded_folder = self._encode_folder_name(folder_name)
        # 先复制，再删除（IMAP 的移动操作）
        self.imap.copy(msg_id, encoded_folder)
        self.imap.store(msg_id, '+FLAGS', '\\Deleted')
        self.imap.expunge()
    
    def apply_label(self, msg_id, label_name):
        """QQ邮箱没有标签，用文件夹代替"""
        folder_name = self.label_folders.get(label_name, label_name)
        
        # 确保文件夹存在 - 需要对文件夹名进行编码
        encoded_folder = self._encode_folder_name(folder_name)
        try:
            # 如果文件夹路径包含斜杠，需要逐级创建父文件夹
            if '/' in folder_name:
                parts = folder_name.split('/')
                current_path = ''
                for part in parts:
                    if current_path:
                        current_path += '/' + part
                    else:
                        current_path = part
                    encoded_current = self._encode_folder_name(current_path)
                    try:
                        self.imap.create(encoded_current)
                    except:
                        pass
            else:
                self.imap.create(encoded_folder)
        except:
            pass
        
        # 移动到对应文件夹
        self.move_to_folder(msg_id, folder_name)
    
    def mark_as_spam(self, msg_id):
        """标记为垃圾邮件"""
        self.move_to_folder(msg_id, 'Junk')
    
    def mark_as_read(self, msg_id):
        """标记为已读"""
        self.imap.store(msg_id, '-FLAGS', '\\Seen')
    
    def delete_email(self, msg_id):
        """删除邮件"""
        self.imap.store(msg_id, '+FLAGS', '\\Deleted')
        self.imap.expunge()
    
    def send_email(self, to_address, subject, body):
        """发送邮件"""
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = self.email_address
        msg['To'] = to_address
        msg['Subject'] = subject
        
        with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
            server.login(self.email_address, self.auth_code)
            server.send_message(msg)
    
    def close(self):
        """关闭连接"""
        if self.imap:
            self.imap.close()
            self.imap.logout()
    
    def __del__(self):
        try:
            self.close()
        except:
            pass