import os
import base64
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup

# 如果修改这些scope，需要删除 token.pickle 文件重新授权
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',  # 读写邮件
    'https://www.googleapis.com/auth/gmail.labels',   # 管理标签
]

class GmailClient:
    def __init__(self):
        self.service = self._get_gmail_service()
        self.labels = self._get_all_labels()
        
    def _get_gmail_service(self):
        """获取Gmail API服务"""
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        return build('gmail', 'v1', credentials=creds)
    
    def _get_all_labels(self):
        """获取所有标签"""
        results = self.service.users().labels().list(userId='me').execute()
        return {label['name']: label['id'] for label in results.get('labels', [])}
    
    def create_label_if_not_exists(self, label_name):
        """如果标签不存在则创建"""
        if label_name not in self.labels:
            label = self.service.users().labels().create(
                userId='me',
                body={
                    'name': label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                }
            ).execute()
            self.labels[label_name] = label['id']
        return self.labels[label_name]
    
    def get_unread_emails(self, max_results=50):
        """获取未读邮件"""
        results = self.service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        emails = []
        
        for msg in messages:
            email_data = self._get_email_detail(msg['id'])
            if email_data:
                emails.append(email_data)
        
        return emails
    
    def _get_email_detail(self, msg_id):
        """获取邮件详情"""
        try:
            msg = self.service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()
            
            payload = msg['payload']
            headers = payload.get('headers', [])
            
            # 提取邮件头信息
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # 提取邮件正文
            body = self._extract_email_body(payload)
            
            return {
                'id': msg_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body[:2000],  # 限制长度
                'snippet': msg.get('snippet', '')
            }
        except Exception as e:
            print(f"获取邮件详情失败: {e}")
            return None
    
    def _extract_email_body(self, payload):
        """提取邮件正文"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        data = part['body']['data']
                        decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        body += decoded
                elif part['mimeType'] == 'text/html':
                    if 'data' in part['body']:
                        data = part['body']['data']
                        decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        soup = BeautifulSoup(decoded, 'html.parser')
                        body += soup.get_text(separator='\n', strip=True)
                elif 'parts' in part:
                    body += self._extract_email_body(part)
        else:
            if 'body' in payload and 'data' in payload['body']:
                data = payload['body']['data']
                decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                if payload['mimeType'] == 'text/html':
                    soup = BeautifulSoup(decoded, 'html.parser')
                    body = soup.get_text(separator='\n', strip=True)
                else:
                    body = decoded
        
        return body.strip()
    
    def apply_label(self, msg_id, label_name):
        """给邮件添加标签"""
        label_id = self.create_label_if_not_exists(label_name)
        self.service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'addLabelIds': [label_id]}
        ).execute()
    
    def mark_as_spam(self, msg_id):
        """标记为垃圾邮件"""
        self.service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'addLabelIds': ['SPAM']}
        ).execute()
    
    def mark_as_read(self, msg_id):
        """标记为已读"""
        self.service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()