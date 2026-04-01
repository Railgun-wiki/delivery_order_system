import json
import sys

def convert():
    try:
        with open('chat.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        md_lines = ["# Chat Export\n"]
        
        for req in data.get('requests', []):
            user_msg = req.get('message', {}).get('text', '')
            if user_msg:
                md_lines.append(f"## 🙋 User\n\n{user_msg}\n")
                
            resp_list = req.get('response', [])
            resp_text = ""
            has_thinking = False
            for r in resp_list:
                if isinstance(r, dict):
                    # 如果是思考节点，记下标志，但忽略内容
                    if r.get('kind') == 'thinking':
                        has_thinking = True
                    # 如果有普通内容，则追加
                    elif 'value' in r and isinstance(r['value'], str):
                        resp_text += r['value']
            
            if has_thinking or resp_text:
                md_lines.append("## 🤖 AI\n")
                if has_thinking:
                    md_lines.append("> 🧠 *[思考过程已折叠/隐藏]*\n")
                if resp_text.strip():
                    md_lines.append(f"{resp_text}\n")
                
        with open('chat_exported.md', 'w', encoding='utf-8') as mf:
            mf.write('\n'.join(md_lines))
        print("Converted successfully to chat_exported.md with thinking stripped!")
    except Exception as e:
        print(f"Error: {e}")

convert()
