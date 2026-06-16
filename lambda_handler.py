from mangum import Mangum
from app.main import app

# Mangum adapts FastAPI/ASGI to AWS Lambda + API Gateway
handler = Mangum(app, lifespan="off")
