import re, os, tempfile
import fitz
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from paddleocr import PaddleOCR

TOTAL_KW = [
    'total', 'grand total', 'amount', 'charged', 'net total', 'net amount',
    'sum', 'subtotal', 'pay', 'payment', 'to pay', 'total amount', 'total due',
    'amount due', 'balance due', 'total cost', 'total paid', 'total price', 'total payment',
    'ยอดรวม', 'ยอดชำระ', 'ยอดชำระเงิน', 'ยอดโอน', 'ยอดที่ต้องชำระ', 'ยอดสุทธิ',
    'ยอดเงินรวม', 'ยอดเงินทั้งหมด', 'ยอดเงิน', 'จำนวนเงิน', 'จำนวนเงินรวม',
    'จำนวนเงินทั้งหมด', 'จำนวนชำระ', 'รวม', 'รวมเป็นเงิน', 'รวมทั้งหมด',
    'รวมสุทธิ', 'รวมเงิน', 'ชำระ', 'ชำระเงิน', 'ชำระด้วยแอป', 'ชำระด้วย',
    'ยอดที่ชำระ', 'ทั้งหมด', 'ทังหมด', 'เงินทั้งหมด', 'โอนเงิน', 'จำนวนเงินโอน',
    'เงินโอน', 'สุทธิ', 'เงินสด', 'มูลค่ารวม', 'ราคารวม', 'ราคาสุทธิ',
    'เรียกเก็บ', 'บาท', 'รับเงิน',
]
SKIP_KW     = [
    # โปรโมชั่น
    'discount', 'ส่วนลด', 'promo', 'voucher', 'coupon',
    # ที่อยู่
    'ถนน', 'ซอย', 'แขวง', 'เขต', 'จังหวัด', 'อำเภอ', 'ตำบล',
    'road', 'street', 'moo', 'หมู่', 'village', 'อาคาร', 'ชั้น',
    # เลขอ้างอิง
    'ref', 'reference', 'เลขที่', 'เลขอ้างอิง', 'รหัส', 'order',
    'tel', 'โทร', 'fax', 'tax id', 'เลขประจำตัว',
]
AMOUNT_RE       = re.compile(r'(?:฿|thb|baht)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', re.IGNORECASE)
SKIP_NUMBER_PAT = re.compile(r'(\d{9,}|\d{1,5}/\d+|\d{1,3}-\d+|0[689]\d{8})')
ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.pdf', '.webp'}


_ocr = PaddleOCR(lang='en')
# ── Preprocess: แก้ปัญหารูปจากกล้องโทรศัพท์ ───────────────────────────────────
def preprocess(image_path):
    img = cv2.imread(image_path)

    # 1. หมุนตามแนวตั้ง ถ้ารูปกว้างกว่าสูง (ถ่ายแนวนอน)
    h, w = img.shape[:2]
    if w > h:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    # 2. ลดขนาดถ้ารูปใหญ่เกิน (กล้องโทรศัพท์ความละเอียดสูงมาก ทำให้ช้า)
    h, w = img.shape[:2]
    if max(h, w) > 2000:
        scale = 2000 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    # 3. เพิ่มความคมชัด
    img = cv2.detailEnhance(img, sigma_s=10, sigma_r=0.15)

    # 4. แปลงเป็น grayscale แล้วเพิ่ม contrast
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    # 5. ลด noise จากกล้อง
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # 6. แปลงกลับเป็น BGR เพราะ PaddleOCR ต้องการ 3 channel
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # บันทึกเป็นไฟล์ชั่วคราว
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.close()
    cv2.imwrite(tmp.name, img)
    return tmp.name


def extract_lines(image_path):
    lines = []
    for page in (_ocr.predict(image_path) or []):
        texts  = page.rec_texts  if hasattr(page, 'rec_texts') else page.get('rec_texts', [])
        scores = page.rec_scores if hasattr(page, 'rec_scores') else page.get('rec_scores', [])
        lines += [t for t, s in zip(texts, scores) if s >= 0.3]
    return lines

def parse_amount(text):
    # ข้ามเบอร์โทร เลขที่อยู่ เลขอ้างอิง
    if SKIP_NUMBER_PAT.search(text):
        return None
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    val = float(m.group(1).replace(',', ''))
    # ข้ามถ้าค่าดูไม่ใช่ราคา (ต่ำกว่า 1 หรือสูงกว่า 100,000)
    if val < 1 or val > 100000:
        return None
    return val

def get_total(image_path):
    # preprocess ก่อนส่งให้ OCR
    processed_path = preprocess(image_path)
    try:
        lines = extract_lines(processed_path)
        totals = []
        for i, line in enumerate(lines):
            ll = line.lower()
            if any(k in ll for k in SKIP_KW):
                continue
            if any(k in ll for k in TOTAL_KW):
                amt = parse_amount(line) or (parse_amount(lines[i + 1]) if i + 1 < len(lines) else None)
                if amt:
                    totals.append(amt)
        if not totals:
            candidates = [parse_amount(l) for l in lines if parse_amount(l) and parse_amount(l) >= 10]
            return max(candidates) if candidates else None
        return max(totals)
    finally:
        try: os.unlink(processed_path)
        except PermissionError: pass

def pdf_to_images(pdf_path):
    paths = []
    for i, page in enumerate(fitz.open(pdf_path)):
        tmp = tempfile.NamedTemporaryFile(suffix=f'_p{i}.png', delete=False)
        tmp.close()
        page.get_pixmap(dpi=200).save(tmp.name)
        paths.append(tmp.name)
    return paths

app = FastAPI(title="Slip OCR")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyse")
async def analyse_slip(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Use jpg, png, pdf, or webp.")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(await file.read())
    tmp.close()

    try:
        targets = pdf_to_images(tmp.name) if ext == '.pdf' else [tmp.name]

        with ThreadPoolExecutor() as executor:
            amounts = list(executor.map(get_total, targets))

        grand_total = sum(a for a in amounts if a)
        return JSONResponse({"grand_total": round(grand_total, 2)})

    finally:
        if ext == '.pdf':
            for target in targets:
                try: os.unlink(target)
                except PermissionError: pass
        try: os.unlink(tmp.name)
        except PermissionError: pass
