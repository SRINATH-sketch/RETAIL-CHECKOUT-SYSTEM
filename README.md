# 🛒 AI Smart Retail Checkout System

## 📌 Project Overview

The AI Smart Retail Checkout System is an intelligent retail billing application that automatically detects products placed inside a shopping basket using Computer Vision and Artificial Intelligence.

The system uses YOLOv11 for product detection and DeepSORT for object tracking. An AI Shopping Agent maintains the shopping cart by adding, updating, and removing products based on tracking IDs. Product prices are fetched from the SQLite database and the total bill is calculated automatically.

---

# Features

- Upload image or video
- Real-time product detection using YOLOv11
- Product tracking using DeepSORT
- AI Shopping Agent for cart management
- Automatic quantity update
- Automatic bill generation
- SQLite product database
- Flask REST API
- React Frontend
- Logging support
- Docker support
- GitHub Actions CI Pipeline

---

# Tech Stack

### Frontend
- React.js
- HTML
- CSS
- JavaScript

### Backend
- Flask
- Python

### AI & Machine Learning
- YOLOv11
- DeepSORT
- OpenCV
- NumPy
- Ultralytics

### Database
- SQLite

### DevOps & MLOps
- Git
- GitHub
- GitHub Actions
- Docker

---

# Project Workflow

1. User uploads an image or video.
2. Flask API receives the file.
3. YOLOv11 detects products.
4. DeepSORT assigns Track IDs.
5. AI Shopping Agent manages the shopping cart.
6. Product information is fetched from SQLite.
7. Quantity and total price are updated.
8. JSON response is sent to the frontend.
9. React displays the shopping cart and total bill.

---

# AI Shopping Agent

The AI Shopping Agent performs the following tasks:

- Maintains the shopping cart
- Adds a product only once using Track ID
- Increases quantity for new physical products
- Removes products leaving the basket
- Fetches product price from SQLite
- Calculates total bill

---

# MLOps Pipeline

Dataset Collection

↓

Data Annotation

↓

YOLOv11 Model Training

↓

Model Evaluation

↓

Model Versioning

↓

Flask API Integration

↓

GitHub Version Control

↓

GitHub Actions CI

↓

Docker Containerization

↓

Deployment

↓

Monitoring & Logging

---

# Project Structure

```
RETAIL-CHECKOUT-SYSTEM
│
├── backend
├── frontend
├── Dockerfile
├── README.md
└── .github
    └── workflows
        └── ci.yml
```

---

# Installation

Clone the repository

```bash
git clone <repository_url>
```

Go to backend

```bash
cd backend
```

Create virtual environment

```bash
python -m venv venv
```

Activate

```bash
.\venv\Scripts\Activate.ps1
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run Flask

```bash
python run.py
```

Run Frontend

```bash
cd frontend
npm install
npm start
```

---

# CI Pipeline

GitHub Actions automatically

- Installs Python
- Installs dependencies
- Verifies backend code
- Reports build status

---

# Docker

Build Image

```bash
docker build -t smart-retail .
```

Run Container

```bash
docker run -p 5000:5000 smart-retail
```

---

# Future Enhancements

- Train custom YOLO model using supermarket dataset
- Live CCTV camera support
- Barcode and QR code integration
- AI recommendation engine
- Multi-camera support
- Customer analytics dashboard
- Cloud deployment
- Full CI/CD deployment pipeline

---

# Author

**G. Srinath**

B.Tech Artificial Intelligence & Machine Learning

Sri Shakthi Institute of Engineering and Technology
