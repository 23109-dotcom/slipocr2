# Slip OCR API

API สำหรับอ่านใบเสร็จและสลิปโอนเงินด้วย PaddleOCR แล้วคืนยอดรวม รองรับภาษาไทยและอังกฤษ

## Features
- อ่านสลิปโอนเงิน ใบเสร็จ ทั้งภาษาไทยและอังกฤษ
- รองรับไฟล์ JPG, PNG, WEBP, PDF
- คืนยอดรวมเงินทั้งหมด

## Installation

```bash
# 1. clone repo
git clone https://github.com/<username>/slip-ocr-api.git
cd slip-ocr-api

# 2. สร้าง virtual environment
python -m venv ocr_env
ocr_env\Scripts\activate

# 3. ติดตั้ง dependencies
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

## API

### POST /analyse

อัปโหลดรูปสลิปแล้วรับยอดรวมกลับมา

**Request**
- Body: `form-data`
- Key: `file` (Type: File)
- Value: รูปภาพหรือ PDF

**Response**
```json
{
    "grand_total": 350.00
}
```

## Test with Postman

1. Method: `POST`
2. URL: `http://127.0.0.1:8000/analyse`
3. Body → form-data → key: `file` (Type: File) → เลือกไฟล์

## Test with Swagger UI

เปิด browser แล้วไปที่:
```
http://127.0.0.1:8000/docs
```

## Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [OpenCV](https://opencv.org/)
- [PyMuPDF](https://pymupdf.readthedocs.io/)
