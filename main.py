from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from typing import List
import os

# .env dosyasını yükle
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Veritabanı bağlantısı
DATABASE_URL = "sqlite:///./content.db"
engine = create_engine(DATABASE_URL, echo=False)

# Uygulama başlat
app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model
class BlogContent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str
    tags: str
    image_url: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Veritabanı tablolarını oluştur
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

# Yardımcı: Temizleme fonksiyonu
def clean(text):
    return text.replace('"', '').replace("“", "").replace("”", "").strip()

# AI içerik üretimi
def generate_ai_content():
    prompt = "Gündemle alakalı yeni bir Türkçe haber başlığı, kısa açıklama ve 3-5 SEO uyumlu etiket üret. Clickbait olmasın."
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Sen yaratıcı bir Türkçe haber editörüsün. SEO uyumlu yaz."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content
    lines = content.split("\n")
    title = clean(next((l.split(":")[1] for l in lines if "başlık" in l.lower()), "Başlık"))
    description = clean(next((l.split(":")[1] for l in lines if "açıklama" in l.lower()), ""))
    tags_line = next((l.split(":")[1] for l in lines if "etiket" in l.lower()), "")
    tags = ",".join([clean(t) for t in tags_line.split(",") if t.strip()])

    return title, description, tags

# Görsel üretimi
def generate_image(prompt):
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        print("Görsel oluşturulamadı:", e)
        return ""

# İçeriği kaydet
def save_to_db(title, description, tags, image_url):
    with Session(engine) as session:
        content = BlogContent(
            title=title,
            description=description,
            tags=tags,
            image_url=image_url,
        )
        session.add(content)
        session.commit()

# ✅ CRON veya manuel: içerik oluştur
@app.post("/auto-generate")
def auto_generate():
    title, description, tags = generate_ai_content()
    image_url = generate_image(title)
    save_to_db(title, description, tags, image_url)
    return {"status": "ok", "message": "İçerik üretildi."}

# ✅ Tüm içerikleri getir
@app.get("/contents", response_model=List[BlogContent])
def get_all_content(skip: int = 0, limit: int = 12):
    with Session(engine) as session:
        statement = select(BlogContent).order_by(BlogContent.created_at.desc()).offset(skip).limit(limit)
        contents = session.exec(statement).all()
        return contents
# ✅ Belirli içeriği ID ile getir
@app.get("/contents/{post_id}", response_model=BlogContent)
def get_single_content(post_id: int):
    with Session(engine) as session:
        content = session.get(BlogContent, post_id)
        if content:
            return content
        raise HTTPException(status_code=404, detail="İçerik bulunamadı")
