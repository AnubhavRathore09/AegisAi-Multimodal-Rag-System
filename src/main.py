from fastapi import FastAPI

from app.main import app as aegis_app


app: FastAPI = aegis_app
