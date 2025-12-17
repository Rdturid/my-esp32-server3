import os
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# ==================== 1. 設定與全域變數 ====================
FONT_PATH = 'NotoSansTC-Regular.ttf'  # 請確認字型檔存在

# 目前顯示與跑馬燈參數狀態
CURRENT_STATE = {
    "text": "Waiting...",
    "size": 16,
    "scroll_delay_ms": 50,    # 新增：捲動延遲（毫秒），越小越快
    "scroll_step": 2          # 新增：每次移動的像素數
}

# 預設按鍵內容 (0-9)
PRESETS = {
    0: "歡迎使用智慧看板",
    1: "包裹已送達",
    2: "垃圾車來了",
    3: "會議中請勿打擾",
    4: "用餐時間",
    5: "外出中",
    6: "請稍候",
    7: "謝謝光臨",
    8: "Happy New Year",
    9: "abc ㄅ ㄆ ㄇ ㄈ"
}

# 字型快取
FONT_CACHE: Dict[str, Dict] = {}

app = FastAPI()

# ==================== 2. 核心功能：文字轉點陣 ====================
def text_to_dot_matrix(text: str, font_path: str, font_size: int) -> List[int]:
    img_size = font_size
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()
    
    img = Image.new('1', (img_size, img_size), 0)
    draw = ImageDraw.Draw(img)
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    if text_width > img_size or text_height > img_size:
        scale = min(img_size / max(text_width, 1), img_size / max(text_height, 1)) * 0.9
        new_size = max(8, int(font_size * scale))
        try:
            font = ImageFont.truetype(font_path, new_size)
        except: pass
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    x = (img_size - text_width) // 2 - bbox[0]
    y = (img_size - text_height) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=1)

    bytes_list = []
    for py in range(img_size):
        for px_start in range(0, img_size, 8):
            byte = 0
            for bit in range(8):
                px = px_start + bit
                if px < img_size:
                    pixel = img.getpixel((px, py))
                    if pixel:
                        byte |= (1 << (7 - bit))
            bytes_list.append(byte)
    return bytes_list

def get_cached_bitmaps(text: str, size: int) -> Dict[str, List[int]]:
    size_key = str(size)
    if size_key not in FONT_CACHE:
        FONT_CACHE[size_key] = {}
    
    result_map = {}
    for char in set(text): 
        if char not in FONT_CACHE[size_key]:
            try:
                dots = text_to_dot_matrix(char, FONT_PATH, size)
                FONT_CACHE[size_key][char] = dots
            except Exception as e:
                print(f"Error generating '{char}': {e}")
                FONT_CACHE[size_key][char] = [0] * ((size*size)//8)
        result_map[char] = FONT_CACHE[size_key][char]
    return result_map

# ==================== 3. API 路由 ====================

@app.get("/", response_class=HTMLResponse)
def webpage():
    presets_html = ""
    for i in range(10):
        presets_html += f"""
        <div class="preset-item">
            <label class="key-label">按鍵 {i}</label>
            <input type="text" name="preset_{i}" value="{PRESETS.get(i, '')}">
        </div>
        """

    html_content = f"""
    <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>跑馬燈控制中心</title>
            <style>
                body {{ font-family: "Microsoft JhengHei", sans-serif; text-align: center; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h2 {{ color: #333; }}
                .status-box {{ background: #e8f5e9; padding: 15px; margin-bottom: 20px; border-radius: 8px; border: 1px solid #c8e6c9; }}
                .status-text {{ color: #2e7d32; font-weight: bold; font-size: 1.3rem; }}
                .status-info {{ margin-top: 8px; font-size: 1rem; color: #1b5e20; }}
                
                input[type="text"], input[type="number"], select {{ 
                    width: 70%; padding: 10px; margin: 8px 0; font-size: 1rem; 
                    border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box;
                }}
                button {{ 
                    background-color: #007bff; color: white; border: none; 
                    padding: 12px 24px; font-size: 1.1rem; border-radius: 5px; 
                    cursor: pointer; margin-top: 20px; 
                }}
                button:hover {{ background-color: #0056b3; }}
                
                .preset-container {{ margin-top: 20px; text-align: left; }}
                .preset-item {{ margin-bottom: 10px; display: flex; align-items: center; }}
                .key-label {{ width: 70px; font-weight: bold; color: #555; }}
                .section-title {{ border-bottom: 2px solid #eee; padding-bottom: 8px; margin: 30px 0 15px; text-align: left; font-weight: bold; }}
                .control-group {{ margin: 15px 0; text-align: left; }}
                label {{ display: block; margin-bottom: 5px; font-weight: bold; color: #444; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>ESP32 智慧跑馬燈控制中心</h2>
                
                <div class="status-box">
                    目前顯示：<br>
                    <span class="status-text">{CURRENT_STATE['text']}</span>
                    <div class="status-info">
                        字體大小：{CURRENT_STATE['size']}px ｜ 
                        速度：{CURRENT_STATE['scroll_delay_ms']}ms ｜ 
                        步長：{CURRENT_STATE['scroll_step']}px
                    </div>
                </div>

                <form action="/submit" method="post">
                    <div class="section-title">即時文字與樣式設定</div>
                    <div class="control-group">
                        <label>顯示文字</label>
                        <input type="text" name="text" placeholder="輸入要顯示的文字..." value="{CURRENT_STATE['text']}">
                    </div>
                    
                    <div class="control-group">
                        <label>字體大小</label>
                        <select name="size">
                            <option value="16" {"selected" if CURRENT_STATE['size']==16 else ""}>小字 (16px)</option>
                            <option value="24" {"selected" if CURRENT_STATE['size']==24 else ""}>中字 (24px)</option>
                            <option value="32" {"selected" if CURRENT_STATE['size']==32 else ""}>大字 (32px)</option>
                        </select>
                    </div>

                    <div class="section-title">跑馬燈動畫設定</div>
                    <div class="control-group">
                        <label>移動速度（毫秒，越小越快）</label>
                        <input type="number" name="scroll_delay_ms" min="10" max="200" step="5" 
                               value="{CURRENT_STATE['scroll_delay_ms']}">
                        <small>建議 20~100，預設 50</small>
                    </div>
                    
                    <div class="control-group">
                        <label>每次移動像素數</label>
                        <input type="number" name="scroll_step" min="1" max="8" step="1" 
                               value="{CURRENT_STATE['scroll_step']}">
                        <small>建議 1~4，越大越「跳」</small>
                    </div>

                    <div class="section-title">遙控器按鍵預設文字 (0-9)</div>
                    <div class="preset-container">
                        {presets_html}
                    </div>

                    <br>
                    <button type="submit">儲存所有設定並更新跑馬燈</button>
                </form>
            </div>
        </body>
    </html>
    """
    return html_content

@app.post("/submit")
async def submit_text(request: Request):
    global CURRENT_STATE, PRESETS
    form_data = await request.form()
    
    # 更新即時顯示文字與字體大小
    new_text = form_data.get("text", "").strip()
    if new_text:
        CURRENT_STATE["text"] = new_text
    CURRENT_STATE["size"] = int(form_data.get("size", 16))
    
    # 更新跑馬燈動畫參數
    try:
        delay = int(form_data.get("scroll_delay_ms", 50))
        CURRENT_STATE["scroll_delay_ms"] = max(10, min(200, delay))  # 限制範圍
    except:
        pass
    
    try:
        step = int(form_data.get("scroll_step", 2))
        CURRENT_STATE["scroll_step"] = max(1, min(8, step))
    except:
        pass
    
    # 更新預設按鍵文字
    for i in range(10):
        val = form_data.get(f"preset_{i}", "").strip()
        if val:
            PRESETS[i] = val
    
    return HTMLResponse(content="<script>alert('所有設定已儲存！跑馬燈即將更新～'); window.location.href='/';</script>")

# ESP32 端取得資料（新增 scroll_delay_ms 和 scroll_step）
@app.get("/get_data")
def get_esp32_data(id: Optional[int] = None):
    global CURRENT_STATE
    
    if id is not None and id in PRESETS:
        CURRENT_STATE["text"] = PRESETS[id]
        print(f"[API] 遙控器切換: 按鍵 {id} → {PRESETS[id]}")

    text = CURRENT_STATE["text"]
    size = CURRENT_STATE["size"]
    
    bitmaps = get_cached_bitmaps(text, size)
    
    return JSONResponse({
        "meta": {
            "text": text,
            "size": size,
            "scroll_delay_ms": CURRENT_STATE["scroll_delay_ms"],
            "scroll_step": CURRENT_STATE["scroll_step"]
        },
        "bitmaps": bitmaps
    })

# ==================== 4. 啟動伺服器 ====================
if __name__ == "__main__":
    if not os.path.exists(FONT_PATH):
        print(f"⚠️ 警告：找不到字型檔 {FONT_PATH}，將使用預設字型")
    
    print("🚀 跑馬燈控制伺服器啟動中...")
    uvicorn.run(app, host="0.0.0.0", port=5000)