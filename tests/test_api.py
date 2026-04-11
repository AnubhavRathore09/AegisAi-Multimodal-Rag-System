import requests

BASE_URL = "http://127.0.0.1:8000"


def test_chat_endpoint():
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": "What is artificial intelligence?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data


def test_rag_query():
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": "Explain machine learning from document"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data


def test_memory_query():
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": "What did I ask before?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data


def test_evaluation_endpoint():
    response = requests.post(
        f"{BASE_URL}/api/evaluate",
        json={
            "query": "What is AI?",
            "response": "AI is artificial intelligence"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
